"""检查类型: commit_file_cap — 单笔提交文件数上限（Task 2611230860，P21）。

上下文：staged_files（列表）、large_commit_reason（显式放行原因，字符串）。
项级参数：max_files（写在 persist.yaml 的检查项上，引擎会合并进 params）。
返回：(passed, detail) 或 (passed, detail, severity_override)；
      引擎约定「覆盖只在失败时生效」，所以「超上限但带放行原因」返回 fail+WARN ——
      整体门禁仍然通过（WARN 不进 hard_fails），这就是「警告放行」。
"""
DEFAULT_MAX = 300


def check(params: dict, context: dict, agent: str) -> tuple:
    staged = context.get("staged_files") or []
    try:
        cap = int(params.get("max_files") or DEFAULT_MAX)
    except (TypeError, ValueError):
        cap = DEFAULT_MAX
    if not staged:
        return True, "skip: 没有暂存文件（空 staged 由别处管）"
    n = len(staged)
    reason = str(context.get("large_commit_reason") or "").strip()
    if n <= cap:
        return True, f"{n} 个文件，未超上限 {cap}"
    if not reason:
        return False, (f"本次暂存 {n} 个文件，超过上限 {cap}；确需一次提交这么多，"
                       f"请用 `--allow-large \"<原因>\"`")
    return False, f"本次暂存 {n} 个文件，超过上限 {cap}；已按原因放行：{reason}", "WARN"
