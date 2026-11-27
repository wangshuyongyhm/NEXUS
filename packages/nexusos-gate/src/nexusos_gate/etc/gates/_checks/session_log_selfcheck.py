"""检查类型: session_log_selfcheck — 会话日志含「自检」与「待决事项」（Task 2611230860，P22）。

一份实现、两处调用：persist 门禁（P22）与 nexus-mem-persist.py 的铁律14 自检都调 evaluate()。
判定：文件不存在/读不了 → 不过；缺「自检」或「待决事项」→ 不过并指出缺哪项。
detail 里带两项各自命中在第几行（便于复核真写了还是凑字）。
"""
from pathlib import Path

ITEM_SELFCHECK = "自检"
ITEM_PENDING = "待决事项"


def evaluate(log_path: str) -> dict:
    """返回 {passed, missing, hits, detail}。hits 是 {项目: 命中行号或 0}。"""
    hits = {ITEM_SELFCHECK: 0, ITEM_PENDING: 0}
    raw = str(log_path or "").strip()
    if not raw:
        return {"passed": False, "missing": [ITEM_SELFCHECK, ITEM_PENDING], "hits": hits,
                "detail": "会话日志不存在: （未提供 session_log_path）"}
    p = Path(raw)
    if not p.is_file():
        return {"passed": False, "missing": [ITEM_SELFCHECK, ITEM_PENDING], "hits": hits,
                "detail": f"会话日志不存在: {raw}"}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return {"passed": False, "missing": [ITEM_SELFCHECK, ITEM_PENDING], "hits": hits,
                "detail": f"会话日志读不了: {type(e).__name__}: {e}"}
    for i, ln in enumerate(lines, 1):
        if not hits[ITEM_SELFCHECK] and ITEM_SELFCHECK in ln:
            hits[ITEM_SELFCHECK] = i
        if not hits[ITEM_PENDING] and ITEM_PENDING in ln:
            hits[ITEM_PENDING] = i
    missing = [k for k, v in hits.items() if not v]
    if missing:
        detail = ("会话日志缺：" + "、".join(missing)
                  + f"（自检命中行={hits[ITEM_SELFCHECK] or '无'}，待决事项命中行={hits[ITEM_PENDING] or '无'}）")
    else:
        detail = f"两项都在（自检 L{hits[ITEM_SELFCHECK]}，待决事项 L{hits[ITEM_PENDING]}）"
    return {"passed": not missing, "missing": missing, "hits": hits, "detail": detail}


def check(params: dict, context: dict, agent: str) -> tuple:
    path = context.get("session_log_path") or params.get("path") or ""
    r = evaluate(path)
    return r["passed"], r["detail"]
