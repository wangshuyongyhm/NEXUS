#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""machine_identities.py — 机器身份名单（单一真源，任务 2611230887）。

名单里是 NEXUS 自己替系统查经验时用的身份：派单、初始化、门禁被拦时替执行者查经验的注入器，
熔炉触发器，监控与自测，消息总线的钩子与兜底实例。这些检索没有哪个 Agent 在干活时看到了结果，
所以默认不记套用；要记必须显式传 annotate=True。真实 Agent 的检索不受影响，HTTP 与 Python 两条路都照记。

使用方：
- nexusos_mem.shared.search：annotate=None 时按 auto_annotate() 取默认值
- nexusos_mem.apply_honesty.is_machine_caller：机器声明只对名单内身份生效
  （apply_honesty 仍可 `from nexusos_mem.apply_honesty import MACHINE_AGENTS`，它从这里转出）
"""

MACHINE_AGENTS = {
    "nexus-monitor", "e2e-drill", "e2esuite", "e2e-suite",
    "nexus-monitor-aggregate", "e2e-suite-drill",
    # 2611230873 补全：熔炉/自测/门禁侧机器身份（不得冒充 Agent 记套用）
    "crucible", "crucible-trigger", "crucible-fragments",
    "e2e-i7-selfcheck",
    # 2611230887 补全：系统替自己查经验的调用方。原名单只管「带了 annotate=false 就不记」那个开关，
    # 管不到默认值，而且没有 xdr-exp-injector——今天它被记了三百多条。
    "xdr-exp-injector",      # 派单/初始化/门禁被拦时替执行者查经验并打包（nexusos_xdr/exp_injector.py）
    "xdr-hook",              # 派单钩子直接拿连接查（nexusos_xdr/dispatchd.py）
    "commit-msg-hook",       # 提交说明钩子：只沉淀经验，不调 search（兜底）
    "nexusos-xdr",           # 消息总线自带知识库实例的兜底身份（没有调用者身份时）
}


def is_machine_identity(agent_id) -> bool:
    """身份是否在机器名单里（名单匹配 strip().lower()，与 is_machine_caller 同口径）。"""
    who = (agent_id or "").strip().lower()
    return who in {n.strip().lower() for n in MACHINE_AGENTS}


def auto_annotate(agent_id) -> bool:
    """search(annotate=None) 的默认值：带身份、且不在机器名单里，才自动记。"""
    return bool((agent_id or "").strip()) and not is_machine_identity(agent_id)
