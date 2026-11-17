"""检查类型: mem_queried — 验证小弟在本 task 周期内有无 MEM search 记录。
G5: done gate 检查小弟是否真正查过 MEM（外部证据：PG agent_activity，不靠自报）。

任务类型分档：
- 分析类（analysis/research/diagnosis）→ 无 search 记录 = fail（REJECT）
- 机械类（mechanical/typo）→ 无 search 也 pass（只 WARN）
- 无 task_type → pass（WARN，向后兼容）

Task 474。
"""

# Task1597 参数化：vault 根经 env/仓内推导解析，不再硬编码本机路径
try:
    from _vault_root import vault_root
except ImportError:  # 包模式加载（gate_engine 以子包形态 import 时）
    from ._vault_root import vault_root

import os
import psycopg2
from datetime import datetime, timezone, timedelta

_ANALYSIS_TYPES = {"analysis", "research", "diagnosis", "investigate", "调研", "分析", "诊断"}

_VAULT_ROOT = vault_root()


def _get_task_type(task_id: str, task_path: str) -> str:
    """获取任务类型。优先 task_state 元数据，fallback 读 task.md frontmatter。"""
    # 方式1: task_state
    try:
        import sys; sys.path.insert(0, os.path.join(_VAULT_ROOT, "05-System/自动化脚本"))
        from nexusos_xdr import task_state
        # Task532 P-d7: 原 task_state.get_task 不存在（AttributeError 被 except 吞
        # → 永远走 fallback）。改 load_state（真实 API）
        ts = task_state.load_state(task_id)
        if ts and ts.get("task_type"):
            return ts["task_type"]
    except Exception:
        pass
    # 方式2: 读 task.md frontmatter（fallback）
    try:
        if task_path:
            tm = os.path.join(os.path.dirname(task_path), "task.md")
            if not os.path.exists(tm):
                tm = os.path.join(task_path, "input", "task.md")
            if os.path.exists(tm):
                with open(tm) as f:
                    in_fm = False
                    for line in f:
                        if line.strip() == "---":
                            if in_fm:
                                break  # frontmatter 结束
                            in_fm = True
                            continue
                        if in_fm and line.startswith("task_type:"):
                            return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _get_task_start_time(task_id: str, agent: str) -> datetime:
    """获取 task 开始时间（dispatch 时间）。从 agent_activity 找该 task 最早事件。"""
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
      agent_field: context 里取 agent_id 的字段名（默认 "source"）
    返回: (passed, detail)
    """
    agent_field = params.get("agent_field", "source")
    callee = context.get(agent_field) or agent
    task_id = context.get("task_id", "")
    task_path = context.get("task_path", "")

    if not callee or callee == "anonymous":
        return True, "anonymous agent，跳过 MEM 查询检查"

    # 查 PG agent_activity
    try:
        start_time = _get_task_start_time(task_id, callee)
        conn = psycopg2.connect(dbname="nexus_mem")
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM agent_activity
            WHERE agent_id = %s AND action = 'search' AND created >= %s
              AND (%s = '' OR task_id = %s)
        """, (callee, start_time, task_id or '', task_id or ''))
        search_count = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        return True, f"PG 查询异常（fail-open 降级）: {type(e).__name__}: {e}"

    if search_count > 0:
        return True, f"✅ 本 task 周期内有 {search_count} 次 MEM search 记录"

    # 无 search 记录，按任务类型判
    task_type = _get_task_type(task_id, task_path).lower()
    if task_type and any(t in task_type for t in _ANALYSIS_TYPES):
        return False, f"❌ 分析类任务（type={task_type}）未查 MEM——B4 禁凭记忆干，done 前必须搜知识库"
    else:
        return True, f"⚠️ 未查 MEM（task_type={task_type or '未知'}，建议查但不拦）"
