---
title: NEXUS Gate 体系 — 声明式门禁引擎
description: 从信息路由到执行路由,场景门禁强制执行(替代靠自觉)
updated: 2026-11-16
---

# NEXUS Gate 体系

> 🔧 Task630 迁移注记：本目录正源位于 pip 包 `nexusos-gate`（`pypi/nexusos-gate/src/nexusos_gate/etc/gates/`），旧位 `nexusos_xdr/etc/gates/` 为指向此处的 symlink（旧 import 路径零破坏）。

> 把 CONSTRAINT 从「读规则靠自觉」升级到「过门禁强制执行」。解决根本问题「规则存在≠规则执行」——约 60 处必做规则此前仅 done 的 4 处有硬拦。
> 设计文档:`../../../../../../nexus-gate-design/2026-07-29-nexus-gate-design.md`

## 架构(三层,可迭代核心)

```
gate_engine.py          ← 调度核心(只管加载YAML+分发插件+汇总,不含检查逻辑)
etc/gates/<场景>.yaml   ← 声明层:场景门禁清单(required_context + items)
etc/gates/_checks/*.py  ← 检查插件(每个文件一个检查类型,启动自动发现)
```

**核心准则(用户强调)**:可迭代性——加新场景/新检查类型不动 engine 核心。检查逻辑独立成插件。

## 当前场景（10 个，261023 实测）

| 场景 | 触发 | YAML | 状态 |
|------|------|------|------|
| done | POST /callback(服务端自动) | done.yaml | ✅ 已迁移 |
| init | POST /session/register 后 | init.yaml | ✅ 在用 |
| dispatch | POST /dispatch 前 | dispatch.yaml | ✅ 在用 |
| persist | 用户说"落盘"后 | persist.yaml | ✅ 在用 |
| code | git commit 前 | code.yaml | ✅ 在用 |
| deploy-sync | 部署后文档同步检查 | deploy-sync.yaml | ✅ 在用 |
| loop_start | LOOP 全自动启动门禁 | loop_start.yaml | ✅ 在用 |
| loop_complete | LOOP 退出前出口门禁 | loop_complete.yaml | ✅ 在用 |
| state_transition | LOOP 状态机转换合法性 | state_transition.yaml | ✅ 在用 |
| user_decision | 发待决/画像代决前门禁 | user_decision.yaml | ✅ 在用 |

## 怎么加新场景(3 步)

1. 写 `etc/gates/<场景>.yaml`(含 required_context + items)
2. 如需新检查类型 → 往 `_checks/` 加插件 .py(见下)
3. 更新 `gate-triggers.yaml`(动作→场景映射,阶段4)

### YAML 规范

```yaml
version: 1
scenario: my_scene
description: 场景描述
required_context:
  - {name: field1, desc: "说明", required: true}
items:
  - id: X1
    name: 检查项名
    auto: true                # false=manual 只列 reminder 不检查
    severity: REJECT          # REJECT(硬拦)/ WARN(软警告)
    check:
      type: field_check       # 对应 _checks/field_check.py
      jsonpath: field1
      min_len: 1
```

## 怎么加新检查类型(1 步,engine 零改动)

往 `_checks/` 丢一个 .py,导出 `check(params, context, agent) -> (bool, str)`,重启 xdr。

```python
# _checks/my_check.py
"""检查类型: my_check — 一句话说明用途"""
def check(params, context, agent):
    """
    params: YAML check 段的参数(引擎已解析 {var} 占位符)
    context: gate 调用时 Agent 传入(required_context 声明的字段)
    agent: 调用方 agent 名
    返回: (passed: bool, detail: str)
    """
    value = context.get(params.get("field", ""))
    return bool(value), f"值={value}"
```

- 文件名 = 检查类型名(YAML `type: my_check` → `my_check.py`)
- 不导出 `check` 函数的 .py 被忽略(防误加载)
- 加载失败的插件记 WARN 跳过(不崩 engine)

## 内置检查插件(46 个)

| 插件 | 检查类型 | 用途 | 用于 |
|------|---------|------|------|
| field_check | 字段非空/长度 | context 字段 len 检查 | G1 files/G2 summary/G3 experiences |
| files_exist | files[] 逐条存在性 | 防幽灵路径（Task898 三级解析 + 2611111773 尾部行内注解剥离：done 回调 files 带「路径（备注）」形态时注解吃进路径误判） | **G1** |
| line_count | 文件行数 | 文件 ≥N 行 | G4 report.md≥30 |
| file_exists | 文件/glob 存在 | 路径或 glob 匹配 | 通用(后续 P1/D1) |
| command | 跑命令判 rc | subprocess + 退出码 | 通用(后续 I3/C5) |
| concurrency_declared | 并发考虑声明 | 三路证据(非代码豁免/`[concurrency:...]`/test_*concurrency* 陪跑) | **C17**（WARN；池 #212） |
| report_schema | 机读状态块 | 尾部围栏含 status 行即认(语义宽容 2611111749:done=complete 同义收编、NEXUS 标记行/围栏方言不强制、next_steps 认多行列表;失败 detail 分围栏/status/next_steps 精准报) | **G12** |
| task_subgraph_connected | 任务子图连通 | 产出登记段+任务目录 .md 全覆盖(wikilink 覆盖判定走 _vaultlink 行级围栏解析:行内 ``` 提及不当开栏,池 #826③) | **G14** |

## 门禁分级

- **REJECT(硬拦)**:动作本身不成立/产出根本缺失(如 files 空、report 不存在)。gate 返回 passed=false,动作被拒。
- **WARN(软警告)**:动作成立,附属质量项没做(如 experiences 空、README 未同步)。passed=true 但记录漏项,供监控发现。

## 怎么调试

```bash
cd 05-System/自动化脚本/nexusos_xdr
# CLI 直接跑(不走 MCP)
python3 gate_engine.py done '{"task_id":"t","files":["a"],"summary":"xxxxxxxxxx","task_path_report":"/etc/hosts"}'
# Python 交互
python3 -c "import sys;sys.path.insert(0,'.');from gate_engine import check;import json;print(json.dumps(check('done',{...}),ensure_ascii=False,indent=2))"
# 跑回归测试
python3 test_gate_engine.py
```

## 诚实边界(不 gate 的)

以下靠人工 review / brainstorming,不进 gate(无法客观自动判定,强拦会误报):
- DRY(是否为单用途引入抽象)
- 阈值掩盖(改阈值的目的)
- 架构优雅(主观判断)

## 观测层(阶段4,待实现)

`gate-triggers.yaml` 定义"动作→必须先过的 gate"映射。xdr 监测动作信号,grace_seconds 内无对应 gate 调用 → 告警"漏调"。nexus-monitor check_M8 算规则执行率。

## 怎么退役

删 YAML + 删插件,engine 自动失效(下次重启不加载)。`/callback` 的 done gate 有降级保底(import 失败时 fallback 到旧 `_run_done_gate`)。

## 关联

- 设计文档:`nexus-gate-design/2026-07-29-nexus-gate-design.md`
- 阶段1计划:`nexus-gate-design/2026-07-29-nexus-gate-plan-phase1.md`
- 回归测试:`nexusos_xdr/test_gate_engine.py`(8 用例,旧 `_run_done_gate` 快照对比)
- 上游集成:`nexusos_xdr/mcp_server.py`(/callback 调 engine + gate_check MCP 工具)
