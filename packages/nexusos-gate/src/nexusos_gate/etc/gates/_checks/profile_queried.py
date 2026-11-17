"""检查类型: profile_queried — 验证决策前本会话是否查过用户画像（641 方案 C，Task651）。

U1: user_decision gate——发待决/代决前，本会话（时间窗内）必须有过画像检索行为。
外部证据：PG agent_activity 的 search 动作（detail.query 命中画像关键词），不靠自报。

口径（仿 mem_queried.py，不自创）：
- 时间窗起点 = 该 agent 近 24h 内最早 activity（与 mem_queried._get_task_start_time 同款）
- 画像关键词 = query 含 画像 / user_profile / profile / 用户定向（652 打标在途，先宽匹配）
- fail-open：PG 异常降级 pass（gate 不因自身故障瘫业务）
"""
import psycopg2
from datetime import datetime, timezone, timedelta

# 画像检索关键词（宽匹配起步；652 打标落地后可收紧到 tag 精确命中）
_PROFILE_KEYWORDS = ("画像", "user_profile", "profile", "用户定向")


def _get_window_start(agent: str) -> datetime:
    """会话窗口起点：该 agent 近 24h 内最早 activity（mem_queried 同款口径）。"""
    try:
        conn = psycopg2.connect(dbname="nexus_mem")
        cur = conn.cursor()
        cur.execute("""
            SELECT MIN(created) FROM agent_activity
            WHERE agent_id = %s AND created > NOW() - INTERVAL '24 hours'
        """, (agent,))
        r = cur.fetchone()
        conn.close()
        if r and r[0]:
            return r[0]
    except Exception:
        pass
    return datetime.now(timezone.utc) - timedelta(hours=24)


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      agent_field: context 里取 agent_id 的字段名（默认 "agent"）
    返回: (passed, detail)
    """
    agent_field = params.get("agent_field", "agent")
    callee = context.get(agent_field) or agent

    if not callee or callee == "anonymous":
        return True, "anonymous agent，跳过画像查询检查"

    try:
        start = _get_window_start(callee)
        conn = psycopg2.connect(dbname="nexus_mem")
        cur = conn.cursor()
        cur.execute("""
            SELECT detail->>'query' FROM agent_activity
            WHERE agent_id = %s AND action = 'search' AND created >= %s
        """, (callee, start))
        queries = [row[0] or "" for row in cur.fetchall()]
        conn.close()
    except Exception as e:
        return True, f"PG 查询异常（fail-open 降级）: {type(e).__name__}: {e}"

    hits = [q for q in queries if any(k.lower() in q.lower() for k in _PROFILE_KEYWORDS)]
    if hits:
        return True, f"✅ 本会话已查过画像（{len(hits)} 次命中，如: {hits[-1][:40]}）"
    return False, (
        f"❌ 本会话（{start.strftime('%H:%M')} 起）无画像检索记录（{len(queries)} 次 search 均未命中"
        f" 画像/user_profile 关键词）——画像代决前必须先查画像（641 U1，MEM :11537）"
    )
