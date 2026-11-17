"""检查类型: readme_synced — 检查 touched_dirs 的 README.md frontmatter 是否同步。
P4 专用(本次教训核心固化:动过目录就要更 README)。

判定规则:
  - touched_dir/README.md 不存在 → 跳过不判（Task1879-A①：无 README 目录不算漏更，防 REJECT 误报）
  - frontmatter.updated == today(date 参数)
  - frontmatter.file_count 与实测相差 < 30%——多口径容差（Task1879-A③）：
    md / 全文件 / 剔缓存(__pycache__+.pytest_cache)全文件 三口径任一命中即同步
"""
import ast
import os
from pathlib import Path

try:
    import _vaultlink
except ImportError:
    from . import _vaultlink

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


def _coerce_dirs(value, context: dict) -> list:
    """把 dirs 参数(可能是 list / str / 占位符未解析)规整成 list[str]。"""
    if value is None:
        return list(context.get("touched_dirs") or [])
    if isinstance(value, list):
        return [str(d) for d in value if d]
    if isinstance(value, str):
        s = value.strip()
        # engine 把 list 占位符解析成 str(list),还原
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [str(d) for d in parsed if d]
            except Exception:
                pass
            # 退化:逗号切分
            inner = s.strip("[]").strip()
            if not inner:
                return []
            return [d.strip().strip("'\"") for d in inner.split(",") if d.strip()]
        # 占位符未解析(缺 context)→ 退回 context
        if s == "" or "{" in s:
            return list(context.get("touched_dirs") or [])
        return [s]
    return [str(value)]


def _parse_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter(--- 包裹)。无 frontmatter 返回 {}。"""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    body = parts[1].strip()
    if not body or yaml is None:
        # 退化:简单 key: value 行解析
        out = {}
        for line in body.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip()
        return out
    try:
        loaded = yaml.safe_load(body)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      dirs: 目录列表(YAML 中写 {touched_dirs};engine 解析后可能成 str)
      date: 期望的 updated 值(YAML 中写 {date})
    返回: (passed, detail)
    """
    dirs = _coerce_dirs(params.get("dirs"), context)
    today = params.get("date") or context.get("date") or ""
    # 占位符未解析兜底
    if isinstance(today, str) and "{" in today:
        today = context.get("date", "")

    # 无动过目录 → 直接通过(本次没动 README,不算漏更)
    if not dirs:
        return True, "无 touched_dirs,跳过 README 同步检查"

    ok, issues = [], []
    for d in dirs:
        p = Path(d).expanduser()
        if not p.is_absolute():
            p = _vaultlink.vault_root() / p  # 相对路径锚 vault 根（gate 进程 cwd 不定，09071853）
        # 传文件路径（如 06-Memory/未决问题池.md）→ 归一到其所在目录查 README（09071853：7 处全误报根治）
        if p.suffix:
            p = p.parent
        readme = p / "README.md"
        if not readme.exists():
            # Task1879-A①: 目录无 README 不算漏更（task/NN/output 等大量目录本就无 README，
            # P4 升 REJECT 后会硬拦一切落盘=误报）——跳过不判
            ok.append(d)
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            issues.append(f"{d}: 读取失败({e})")
            continue

        fm = _parse_frontmatter(text)
        if not fm:
            issues.append(f"{d}: 无 frontmatter")
            continue

        # updated 检查
        if today:
            updated = str(fm.get("updated", "")).strip()
            if updated != str(today).strip():
                issues.append(f"{d}: updated={updated or '空'} ≠ {today}")

        # file_count 合理性——Task1879-A③ 多口径容差（1877 后全库双口径并存：
        # 「全文件口径」（01-Projects 4991）/「md 口径」（06-Memory 8308）/
        # 「剔缓存全文件口径」（自动化脚本 1845 剔 __pycache__/.pytest_cache）。
        # 声明值与任一口径实测相差 <30% 即算同步，全不命中才判漏更。
        try:
            declared = int(fm.get("file_count", -1))
        except (TypeError, ValueError):
            declared = -1
        if declared >= 0:
            actual_md = 0
            actual_files = 0
            actual_files_nocache = 0
            try:
                for _root, _dirs, _files in os.walk(p):
                    in_cache = "__pycache__" in _root or ".pytest_cache" in _root
                    actual_files += len(_files)
                    if not in_cache:
                        actual_files_nocache += len(_files)
                    actual_md += sum(1 for _f in _files if _f.endswith(".md"))
            except Exception:
                actual_md = actual_files = actual_files_nocache = -1
            if actual_md >= 0:
                # (口径名, 实测值, 偏差, 容差)
                calibers = []
                for label, actual in (
                    ("md", actual_md),
                    ("全文件", actual_files),
                    ("剔缓存全文件", actual_files_nocache),
                ):
                    tol = max(3, int(actual * 0.3))
                    calibers.append((label, actual, abs(declared - actual), tol))
                if not any(diff <= tol for _, _, diff, tol in calibers):
                    label, actual, diff, tol = min(calibers, key=lambda c: c[2] - c[3])
                    actuals_str = "/".join(f"{l}={a}" for l, a, _, _ in calibers)
                    issues.append(
                        f"{d}: file_count={declared} vs 实测({actuals_str}) 全不命中(最小差 {diff} 超容差 {tol})"
                    )
        ok.append(d)

    if issues:
        return False, f"{len(issues)} 处 README 漏更: " + "; ".join(issues)
    return True, f"{len(dirs)} 个目录 README 已同步(updated={today or 'N/A'})"
