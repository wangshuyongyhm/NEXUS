# Agent Providers 语义（NEXUS_AGENT_PROVIDERS）

> Task 1577 目标 3——key 配置层与调度层共享同一注册表（接口占位阶段）。

## 单一真源

`~/.nexus/providers.json`（env `NEXUS_AGENT_PROVIDERS` 可重定向）：

- 由 `nexus setup` 向导增删改（内置六平台出厂预置，可删可恢复）
- schema 见 `src/nexus_oss/providers.py` 模块 docstring（version 1）

## 两类消费者

| 消费者 | 读法 | 用途 |
|--------|------|------|
| **配置层**（向导） | `setup_wizard.py` → `providers.load_providers()` / `add_provider()` / `remove_provider()` | 表单动态渲染 + 页内增删 |
| **调度层**（xdr / agent-registry，占位） | `providers.configured_providers(env_file=None)` | 感知「哪些平台已配好 key」——新平台加入后调度层可见 |

## configured_providers() 契约（调度层接入点）

```python
from nexus_oss.providers import configured_providers

rows = configured_providers()
# [{"id": "zhipu", "label": "智谱 BigModel（GLM）", "builtin": True,
#   "ready": True,  "missing": []}, ...]
```

- `ready=True`：该平台全部字段已在 `~/.nexus/.env` 配置（dispatch-ready）
- `missing`：缺哪些 env 变量名（提示补配，不阻塞）
- 幂等只读；注册表缺失时自愈生成出厂预置（与向导一致）

## 调度逻辑本体接入（不在 1577 scope）

xdr 派单选 Agent 时如何用这份注册表（如按 provider 映射 agent 能力卡）属
调度语义设计——当前交付止步于本读取接口 + CLI 可见性命令：

```bash
~/.nexus/venv/bin/nexus providers   # 人读版同一信息（L3/运维自查看）
```

后续单接入时：import 上述函数即可，勿绕过注册表直接读 .env（字段名真源
在 providers.json 的 fields 里，key 值真源在 .env——两者分离是刻意的：
注册表可提交进仓库作为出厂默认，值永不在仓库）。
