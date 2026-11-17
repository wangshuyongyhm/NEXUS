"""检查类型: outcome_filled — G10 真套用口径（T657 修3；Task983 覆盖扩展）。

检查**本任务 + 该 agent 当日全部**的 apply_attempt 中真套用的是否已回填。
口径真源：nexusos_mem.apply_honesty.is_real_apply（Task546 三态，U8 定稿
2026-08-17）——不在此自创第二口径。

三态判据（is_real_apply）：
  1. attempt.outcome 非空且非 pending → 真套用且已回填 → 无欠账
  2. outcome pending/缺失 但 attempt.created 起 24h 内 report 引用
     MEM#<target_id> → 真套用未回填 → 欠账（REJECT）
  3. pending/缺失且无产物引用 → 查证式命中（普通查询稀释）→ 不计入
     （治 654 补账实锤：查 MEM 产生新 annotate attempt 又被 G10 抓的打地鼠）

覆盖（Task983，09010832 数据体检：44/54=81.5% 欠账，旧覆盖只抓本 task
窗口漏掉跨 task 的当日欠账）：本 task_id 全窗口 ∪ source agent 当日全部。
旧口径（裸抓全部 pending attempt）保留为 is_real_apply 不可用时的降级。
"""


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params: (无特殊参数)
    context: task_id（done gate required）

    返回: (passed, detail)
    """
    task_id = context.get("task_id", "")
    if not task_id:
        return True, "无 task_id，跳过 outcome 回填检查"

    try:
        import psycopg2
        conn = psycopg2.connect("dbname=nexus_mem")
        cur = conn.cursor()
        # Task983 覆盖扩展：本 task 全窗口 ∪ 该 agent 当日全部（agent 空/调试值
        # 时退回仅本 task，防 cli 手跑误抓全 agent 的当日 pending）
        scope_note = ""
        if agent and agent not in ("cli", ""):
            cur.execute(
                "SELECT id, target_id, outcome, created FROM agent_activity "
                "WHERE action='apply_attempt' "
                "AND (task_id=%s OR (agent_id=%s AND created >= CURRENT_DATE))",
                (task_id, agent)
            )
            scope_note = f"（覆盖：task {task_id} + {agent} 当日全部）"
        else:
            cur.execute(
                "SELECT id, target_id, outcome, created FROM agent_activity "
                "WHERE action='apply_attempt' AND task_id=%s",
                (task_id,)
            )

        attempts = [
            {"id": _id, "target_id": _tid, "outcome": _oc, "created": _cr}
            for _id, _tid, _oc, _cr in cur.fetchall()
        ]
        if not attempts:
            cur.close()
            conn.close()
            _hint_b5 = ""
            if not task_id.startswith("xdr-"):
                _hint_b5 = "（注意：非 xdr-{to}-{ts}-{hex} 格式，若小弟确有 search 套用请核对 task_id 是否与 dispatch 一致）"
            return True, f"task_id={task_id} 无 apply_attempt（未套用经验），无需回填{_hint_b5}"

        try:
            from nexusos_mem.apply_honesty import is_real_apply
        except ImportError:
            is_real_apply = None  # 口径真源不可用 → 降级旧口径（全部 pending 计入）

        unfilled = []
        for a in attempts:
            outcome = a.get("outcome")
            if outcome and outcome != "pending":
                continue  # 态1: 已回填
            # 兼容旧回填路径：apply_outcome 行写 detail 不写 attempt.outcome 列
            cur.execute(
                "SELECT detail->>'result' FROM agent_activity "
                "WHERE action='apply_outcome' AND target_id=%s "
                "AND detail->>'apply_attempt_id'=%s "
                "ORDER BY created DESC LIMIT 1",
                (a["target_id"], str(a["id"]))
            )
            row = cur.fetchone()
            if row and row[0] and row[0] != "pending":
                continue  # 旧路径已回填
            if is_real_apply is not None:
                try:
                    if not is_real_apply(a):
                        continue  # 态3: 查证式命中不计入（U8）
                except Exception:
                    pass  # 判不了 → 按套用处理（保守回填提示）
            unfilled.append((a["target_id"], a["id"]))

        cur.close()
        conn.close()
        if unfilled:
            sample = ", ".join(f"exp_id={e}(attempt={a})" for e, a in unfilled[:3])
            return False, (
                f"{len(unfilled)} 条真套用 apply_attempt 未回填真实 outcome（仍 pending/缺失）: {sample}. "
                "POST /apply_outcome {\"agent_id\":\"<你\",\"knowledge_id\":<exp_id>,\"outcome\":\"success|partial|failed|not_applicable\",\"evidence\":\"...\"}"
                "（knowledge_id 自动解析最新 pending attempt，无需 attempt_id；或原生 apply_attempt_id+exp_id+result）"
                f"（查证式命中已按 U8 口径排除）"
            )
        return True, f"{len(attempts)} 条 apply_attempt 无真套用欠账（已回填或查证式不计入）{scope_note}"
    except Exception as e:
        # DB 错误 fail-open（不阻断 done）
        return True, f"outcome 回填检查异常（fail-open）: {type(e).__name__}: {e}"
