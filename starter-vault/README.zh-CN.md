# starter-vault —— NEXUS 约束层，开箱即用

> **给 Agent 的「约束即代码」。** 本包是 NEXUS 部署的声明式规则层：
> 纯 Markdown + YAML，自己没有守护进程。

## 这是什么

一份 vault 起步包。它让舰队里每个 Agent 拿到同一本小而可执行的规则——
纪律由机器校验，而不是靠自觉。一句话哲学：*没有机器执行的规则只是愿望。*

## 内容清单

| 文件 | 何时读 |
|---|---|
| `AGENTS.md` | 由 Agent 宿主常驻加载（各家注入点不同——见 docs/agents/） |
| `quickref.md` | 每次会话开始——三个门禁时刻一页纸 |
| `task-spec.md` | 写或收任务书时 |
| `protocols.md` | 派发、落盘、在场协调时 |
| `gates/init.yaml` | 会话启动门禁（配置在位、服务可达） |
| `gates/dispatch.yaml` | 派单前门门禁（任务书在位、目标已声明） |
| `gates/persist.yaml` | 关单门禁（产出在位、声明经验证） |
| 英文原版 | 同目录无后缀文件（与本中文版逐节对齐） |

## 怎么用

0. **安装门禁引擎**（二选一）：

   ```bash
   # pipx（推荐）：
   pipx install nexusos-gate nexusos-xdr
   # 或本地路径安装：
   pip install -e /path/to/pypi/nexusos-gate
   ```

   quickref.md 里的 `gate_check` 工具来自 nexus-xdr MCP 服务（总线上的
   `/mcp`）——按 docs/agents/ 的片段配置你 Agent 的 MCP 客户端，或直接调
   引擎 CLI：`python -m nexusos_gate.gate_engine <scenario> '<json-context>'`。

1. **把门禁引擎指向这些场景：**

   ```bash
   export NEXUS_GATES_DIR=/path/to/starter-vault/gates
   ```

2. **注入 `AGENTS.md`** 到你的 Agent 的指令位（各家不同——向导会为每个
   探测到的 Agent 打印正确的那个）。

3. **自定义靠编辑，不靠分叉。** YAML 场景是数据：加一行检查、调一个级别、
   或把 `cmd` 指到你自己的脚本。用户自定义检查也可以放
   `$NEXUS_HOME/gate/checks.d/*.yaml`，会叠加加载。

## 门禁执行什么

- **REJECT**——硬拦：动作不发生（缺任务书、缺产出、环境宕）。
- **WARN**——软警告：记录在案，知情继续。

done 回调路径自动校验；另两个场景在会话启动与派单前运行。

## 布局注记（向导对接）

安装向导（`nexus init`）可以生成与本包完全一致的新 vault
（`starter-vault` → 你的 vault 根）。已有 Markdown 目录就直接把这些文件
放进去——约束层是内容不是工具，不依赖任何特定 vault 应用。
