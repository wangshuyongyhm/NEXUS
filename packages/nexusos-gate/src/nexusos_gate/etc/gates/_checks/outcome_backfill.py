"""P18 outcome_backfill — 主控套用经验 outcome 回填检查（Task1951 G3=清单 P4）.

口径（首期 WARN 观察一周，#464）：
- 当日该 agent 的 apply_attempt 行集合 A（agent_activity）
- apply_outcome 行 detail->>'apply_attempt_id' ∈ A 且 detail->>'result' != 'pending'
  → 计为已回填
- |A| - 已回填数 > 0 → WARN（套用未回填，经验永远 pending = 认知诚实失职）
- PG 不可达/无套用 → pass 附注（fail-open，WARN 级不阻塞）
"""
from __future__ import annotations


def check(params: dict, context: dict, agent: str) -> tuple:
    if not agent:
        return True, "P18: 无 agent 参数——skip"
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=nexus_mem")
        cur = conn.cursor()
        cur.execute(
            "SELECT id, COALESCE(outcome,'') FROM agent_activity "
            "WHERE action='apply_attempt' AND agent_id=%s AND created::date=CURRENT_DATE",
            (agent,))
        rows = cur.fetchall()
        attempt_ids = [r[0] for r in rows]
        if not attempt_ids:
            cur.close(); conn.close()
            return True, "P18: 当日无 apply_attempt——无需回填"
        # 2611231129 甲（池#1233）：日径一——套用记录自己那一行的结果列
        # （结案工具直接把记录写成 not_applicable 时不产生 apply_outcome 动作行，
        #  旧口径只数动作行，47 条全有结果仍报 43 条未回填）
        by_column = {r[0] for r in rows
                     if str(r[1] or "").strip() and str(r[1]).strip() != "pending"}
        # 口径二——存在有效的给结果动作行（pending 不算；已让位的行不算）
        cur.execute(
            "SELECT DISTINCT detail->>'apply_attempt_id' FROM agent_activity "
            "WHERE action='apply_outcome' AND created::date >= CURRENT_DATE - 1 "
            "AND detail->>'result' <> 'pending' "
            "AND COALESCE(detail->>'superseded','') <> 'true' "
            "AND detail->>'apply_attempt_id' = ANY(%s)",
            ([str(i) for i in attempt_ids],))
        by_action = {r[0] for r in cur.fetchall() if r[0]}
        backfilled = by_column | by_action
        cur.close(); conn.close()
    except Exception as e:
        return True, "P18: PG 不可达（%s）——fail-open pass" % str(e)[:80]

    missing = len(attempt_ids) - len(backfilled)
    if missing > 0:
        return False, ("P18 outcome 回填: 当日 %d 条 apply_attempt，已回填 %d"
                       "（结果列 %d + 动作行 %d）——%d 条未回填"
                       "（B5 用完经验回填 outcome，防经验永远 pending）"
                       % (len(attempt_ids), len(backfilled), len(by_column),
                          len(by_action - by_column), missing))
    return True, ("P18: 当日 %d 条套用全部有 outcome 回填"
                  "（结果列 %d + 动作行 %d）"
                  % (len(attempt_ids), len(by_column), len(by_action - by_column)))
