"""检查类型: parent_anchors — 任务书父锚校验（Task592 D6，防断链环源头拦）。

task-spec §1 第9项：任务书必须含 parent_anchors 段（≥1 个 [[锚]]，标注任务
从哪来：未决池行/项目MOC/事物页/上级任务），且每个锚目标在 Vault 真实存在
（路径或 basename 解析，对齐 Obsidian 规则）。防「任务产出无父可归」的断链增量。

宽限设计（任务书§7 陷阱：上线即 REJECT 会拦掉所有旧格式任务书）：
  GRACE_END（08-20 00:00）前缺锚/锚不存在 → 放行但 detail 报清单（WARN 语义）；
  之后自动切 REJECT，无需人工改 yaml。
"""
import re
from pathlib import Path

try:
    import _vaultlink
except ImportError:
    from . import _vaultlink

_ANCHOR_SECTION_RE = re.compile(r"parent_anchors?\s*[::]", re.IGNORECASE)

# 池 #826②（B3）：锚分两类——库内锚（[[未决问题池]] 这类 basename/wikilink，指向
# 知识页或池行，"可解析"就是它的验法）vs 路径锚（含 "/" 的 vault 内路径，如
# task/NN-xxx/output/report）。路径锚必须**按路径**验存在，不许走 basename 兜底：
# 否则目标文件被删/移后，同名笔记在别处仍能让它"解析成功"= 假绿。
def _is_path_anchor(anchor: str) -> bool:
    return "/" in anchor.strip().strip('"')


def _path_anchor_exists(anchor: str) -> bool:
    """路径锚严格判定：直接按 vault 相对路径找文件/目录（不带 basename 兜底）。"""
    raw = anchor.strip().strip('"')
    try:
        root = _vaultlink.vault_root()
    except Exception:
        return True  # vault 根不可得时 fail-open（宁漏勿滥，同 _vaultlink 口径）
    cand = root / raw
    if cand.is_file() or cand.is_dir():
        return True
    return (root / (raw + ".md")).is_file()


def _extract_anchors(task_md_path: str) -> list:
    """从 task.md 提取 parent_anchors 段的 [[锚]] 列表（无段/无锚返回 []）。"""
    try:
        text = Path(task_md_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = _ANCHOR_SECTION_RE.search(text)
    if not m:
        return []
    # 段切片：从声明到下一个空行/标题（单行与多行列表都兼容）
    tail = text[m.end():]
    section = re.split(r"\n\s*\n|\n#", tail, maxsplit=1)[0]
    section = m.group(0) + section  # 同行声明的锚也要（parent_anchors: [[X]]）
    return _vaultlink.extract_wikilinks(section)


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params: (无特殊参数)
    context: task_dir（dispatch gate required）
    返回: (passed, detail)
    """
    task_dir = context.get("task_dir", "")
    task_md = str(Path(task_dir) / "input" / "task.md")
    if not Path(task_md).is_file():
        # 池 #826②（B3）：缺文件不是"跳过"——静默 pass 就是假绿。D1 会同时报存在性，
        # 这里如实说明"锚校验无法进行"，让缺文件的任务在 dispatch 侧有两条一致的证据。
        return False, (
            f"task.md 不存在（{Path(task_md).parent}），父锚无法校验"
            "——这不是「跳过」：缺任务书先修 D1 项"
        )

    anchors = _extract_anchors(task_md)
    if not anchors:
        detail = "任务书缺 parent_anchors 段（task-spec §1 第9项：≥1 个 [[锚]] 标注来源——未决池行/项目MOC/事物页/上级任务）"
        if _vaultlink.in_grace():
            return True, f"[宽限至08-20] D6 放行: {detail}"
        return False, detail

    missing_path = [a for a in anchors if _is_path_anchor(a) and not _path_anchor_exists(a)]
    missing_wiki = [a for a in anchors if not _is_path_anchor(a) and not _vaultlink.resolve_target(a)]
    missing = missing_path + missing_wiki
    if missing:
        parts = []
        if missing_path:
            parts.append(f"路径锚目标文件不存在: {missing_path}")
        if missing_wiki:
            parts.append(f"库内锚无法解析: {missing_wiki}")
        detail = ("parent_anchors 锚不存在——" + "；".join(parts)
                  + "（路径锚按 vault 内路径严格验；库内锚按 basename 解析，检查拼写或补建目标页）")
        if _vaultlink.in_grace():
            return True, f"[宽限至08-20] D6 放行: {detail}"
        return False, detail
    return True, f"父锚校验通过: {len(anchors)} 个锚均可解析 {anchors[:3]}"
