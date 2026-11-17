"""检查类型: experiences_present — G3 二选一语义（T657 修2 + 1416 修）。

回调 experiences 数组 ≥1 **或** 本任务时间窗内该任务执行者在 MEM DB 有
knowledge 写入（PG 查 source_agent + 时间窗），二选一过。

治 648 聚类实证的全量 FAIL 第一位（G3 84 项）：agent 写 DB 不写回调数组
是主流行为（kimi 649 实案：写 MEM#61695 但回调数组空 → G3_REJECT 误伤）。

1416 修（池#G3盲区行 09181954 两例）：误 REJECT 根因不是"只查 agent_activity"——
knowledge 联查 T657 就有；真根因是**判定 agent 信任了调用方参数**。主控终验
CLI 跑 done gate 时 NEXUS_AGENT=主控自己（hermes/zcode），G3 拿错误 agent 查
"窗内无该 agent 写入"→ 误 REJECT（oc MEM#73384/kimi #73411 窗内实存实证）。
修复：判定 agent 优先取任务状态 callee（任务执行者），调用方 agent 参数仅兜底。
"""


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params: (无特殊参数)
    context: experiences（回调数组）、task_id（时间窗锚点）

    返回: (passed, detail)
    """
    exps = context.get("experiences") or []
    if len(exps) >= 1:
        return True, f"回调 experiences {len(exps)} 条"
    if not agent:
        return False, "'experiences' 长度 0 < 1（且无 agent 无法查 DB 写入）"
    try:
        import psycopg2
        from datetime import datetime, timezone, timedelta
        # 时间窗：任务 created → now（load 不到回退 24h——任务书"本任务时间窗"）
        # 1416 修：判定 agent 优先取任务执行者（callee）——终验/接力场景调用方
        # 署名≠执行者时不再误报（09181954 两例根因）；load 失败才用 agent 参数兑底。
        since = None
        effective_agent = agent
        try:
            from nexusos_xdr import task_state as _ts
            _st = _ts.load_state(context.get("task_id") or "") or {}
            _c = _st.get("created")
            if _c:
                since = datetime.fromisoformat(str(_c).replace("Z", "+00:00"))
            _callee = _st.get("callee")
            if _callee:
                effective_agent = _callee
        except Exception:
            since = None
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
        conn = psycopg2.connect("dbname=nexus_mem")
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM knowledge "
            "WHERE source_agent=%s AND created >= %s AND NOT deprecated",
            (effective_agent, since),
        )
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        if n >= 1:
            return True, (f"回调数组空但 MEM DB 时间窗内 {effective_agent} 有 {n} 条写入"
                          f"（since={since.isoformat()[:19]}）")
        return False, ("'experiences' 长度 0 < 1 且 MEM DB 时间窗内无该 agent 写入"
                       f"（{effective_agent}, since={since.isoformat()[:19]}）")
    except Exception as e:
        # DB 异常：回退原数组语义（空=不通过，与旧行为一致）
        return False, (f"'experiences' 长度 0 < 1；DB 查询异常 fail-closed 同旧语义"
                       f"（{type(e).__name__}: {str(e)[:60]}）")
