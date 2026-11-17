"""检查类型: agent_archive_updated — 动过 Agent 目录时检查经验档案 updated 字段。
P10: persist gate WARN 级——08110853 痛点固化（漏更 Agent 档案）。

判定：touched_dirs 含 05-System/Agent/<name>/ → 检查 <name>/经验与坑.md frontmatter updated == date。
只查字段，"是否该更"需 LLM 判断不可自动化（MEM#42862）。
Task 483-patch1：修复 list 占位符陷阱。
"""
import ast
import re
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


def _coerce_list(value):
    """把 value 规整成 list[str]。处理 gate_engine 占位符传来的 "[]" 字符串。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(d) for d in value if d]
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("["):
            try:
                parsed = ast.literal_eval(s)
                return [str(d) for d in parsed if d] if isinstance(parsed, list) else []
            except Exception:
                return []
        return [s] if s else []
    return [str(value)] if value else []


def _parse_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter（--- 包裹）。"""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    body = parts[1].strip()
    if not body or yaml is None:
        out = {}
        for line in body.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
        return out
    try:
        loaded = yaml.safe_load(body)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      dirs: touched_dirs 列表
      date: 日期 YYYY-MM-DD
    返回: (passed, detail)  # severity WARN
    """
    dirs = _coerce_list(params.get("dirs", []))
    if not dirs:
        dirs = _coerce_list(context.get("touched_dirs", []))

    date = params.get("date", "")

    # 找 Agent 目录路径
    agent_dirs = []
    for d in dirs:
        d_str = str(d)
        match = re.search(r"05-System/Agent/(\w+)", d_str)
        if match:
            agent_dirs.append((match.group(1), d_str))

    if not agent_dirs:
        return True, "无 Agent 目录改动，跳过档案检查"

    issues = []
    for agent_name, _ in agent_dirs:
        archive_path = Path(f"05-System/Agent/{agent_name}/经验与坑.md")
        if not archive_path.exists():
            issues.append(f"{agent_name}/经验与坑.md 不存在")
            continue
        try:
            content = archive_path.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            updated = str(fm.get("updated", ""))
            if date and updated != date:
                issues.append(f"{agent_name}/经验与坑.md updated={updated} != {date}")
        except Exception as e:
            issues.append(f"{agent_name} 读取异常: {e}")

    if issues:
        return False, f"⚠️ Agent 档案可能未更新: {'; '.join(issues[:3])}"
    return True, f"✅ {len(agent_dirs)} 个 Agent 档案 updated 字段已同步"
