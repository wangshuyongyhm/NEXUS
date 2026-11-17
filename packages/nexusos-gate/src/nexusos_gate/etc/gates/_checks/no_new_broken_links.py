"""检查类型: no_new_broken_links — 产出零新断链（Task592 G11，done 时修成本最低）。

扫描本任务 output/ + input/ 全部 .md 的 [[链接]]（剥离 ``` 代码块防数据误报），
逐个解析（路径/basename 双解析，对齐 Obsidian）；有断链=REJECT 列出，全部可解析=过。

豁免: task.dispatched.*.md（xdr 自动生成副本，含 exp_injector 注入内容，
非任务书作者产物——其断链归注入源治理，不在本任务拦截面）。
"""
from pathlib import Path

try:
    import _vaultlink
except ImportError:
    from . import _vaultlink


def _task_root(context: dict) -> Path:
    """task_path 兼容两种形态：task.md 文件路径 / 任务目录。"""
    tp = context.get("task_path", "") or ""
    p = Path(tp)
    if p.is_dir():
        return p
    if p.name == "task.md":
        return p.parent.parent
    return p


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params: (无特殊参数)
    context: task_path（done gate 提供任务路径）
    返回: (passed, detail) — REJECT 级（severity 在 YAML）
    """
    root = _task_root(context)
    if not root.is_dir():
        return True, "任务目录不可解析，跳过断链检查"

    broken = []  # [(file_rel, target), ...]
    checked = 0
    for sub in ("output", "input"):
        d = root / sub
        if not d.is_dir():
            continue
        for md in d.rglob("*.md"):
            if ".dispatched." in md.name:  # 自动生成副本豁免
                continue
            checked += 1
            try:
                text = md.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for target in _vaultlink.extract_wikilinks(text):
                if not _vaultlink.resolve_target(target):
                    broken.append((str(md.relative_to(root)), target))

    if broken:
        sample = "; ".join(f"{f}→[[{t}]]" for f, t in broken[:5])
        return False, (f"产出含 {len(broken)} 条新断链（done 时修，成本最低点）: "
                       f"{sample}{' ...' if len(broken) > 5 else ''}")
    return True, f"产出零新断链（{checked} 个 .md 全部链接可解析）"
