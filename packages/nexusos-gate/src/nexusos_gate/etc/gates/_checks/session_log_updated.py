"""检查类型: session_log_updated — 会话日志不只是存在，必须本次会话更新过。
P7: persist gate 检查 session_log 含 session_id 字符串（条件 A）或 mtime >= session_start_ts（条件 B）。

Task 483：08110853 痛点固化——zcode 报"闭环"但漏更新会话日志。
"""
import os
from pathlib import Path


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      path: 会话日志文件路径
      session_id: 本次会话 ID（如 "08110853"）
      session_start_ts: 本次会话开始 unix timestamp（float）
    返回: (passed, detail)
    """
    log_path = params.get("path", "")
    session_id = params.get("session_id", "")
    session_start_ts = params.get("session_start_ts")

    if not log_path:
        return True, "skip: 无 session_log_path（P1 负责'存在'检查）"

    p = Path(log_path)
    if not p.exists():
        return True, "skip: 文件不存在（P1 负责'存在'检查）"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return True, "skip: 读取异常（P1 负责存在性）"

    # 条件 A：内容含 session_id（更可靠，Obsidian sync 刷 mtime 不影响）
    if session_id and session_id in content:
        return True, f"✅ 会话日志含 session_id={session_id}"

    # 条件 B：mtime >= session_start_ts（兜底）
    if session_start_ts:
        try:
            ts = float(session_start_ts)
            mtime = p.stat().st_mtime
            if mtime >= ts:
                return True, f"✅ 会话日志 mtime({mtime:.0f}) >= session_start({ts:.0f})"
            return False, f"❌ 会话日志 mtime({mtime:.0f}) < session_start({ts:.0f})，未更新"
        except (ValueError, TypeError):
            pass  # ts 解析失败，fail-open

    # session_id 不在内容 + 无有效 ts → 无法确认更新
    if session_id:
        return False, f"❌ 会话日志不含 session_id={session_id}，且 mtime 无法验证更新"
    return True, "⚠️ 无 session_id 参数，跳过更新检查（fail-open）"
