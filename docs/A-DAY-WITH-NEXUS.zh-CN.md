# 和 NEXUS 过一天——你的第一天真实长这样

> 这是装好 NEXUS 之后第一天的完整走查。文中每条命令、每个能力都来自当前
> 发布物——不承诺没发布的东西。哪一步今天还是手动的，我们明说。

## 早上：安装与初始化

克隆仓库，跑安装器。它探测依赖、建隔离环境、生成你的配置：

```bash
git clone https://github.com/wangshuyongyhm/NEXUS.git nexus-oss && cd nexus-oss
./install.sh
```

然后是一次性的 schema 步骤（今天它是一个写明的手动步骤——向导会帮你
建库，但还不会替你应用 schema）：

```bash
createdb nexus_mem 2>/dev/null; psql -d nexus_mem -c 'CREATE EXTENSION IF NOT EXISTS vector'
psql -d nexus_mem -f db/schema.sql
```

接着是向导。输入「初始化」——或直接跑：

```bash
nexus init
```

向导扫描你的环境（只读），缺什么用固定选项协商而不是开放题；没有
PostgreSQL 就替你装，有就在你的库里建一个最小权限的专属库；探测你机器
上装着的 AI Agent；把配置写进 `~/.nexus/`。以后重复跑是安全的——doctor
模式只报漂移。

## 上午续：你的 vault 醒了

向导还会把约束层铺进你的 vault：`AGENTS.md`、一页 `quickref.md`、任务书
契约、三条线上协议、三个门禁场景（init/dispatch/persist）。从现在起你的
Agent 读这些——规则是 Markdown，不是魔法。

你的会话以 quickref 教的仪式开始：注册在场、看谁在线、给服务做体检：

```bash
curl -s -X POST http://127.0.0.1:19998/session/register \
  -d '{"agent":"my-agent","role":"executor","session_id":"my-agent-day1","status":"init"}'
curl -s http://127.0.0.1:19998/session/active
```

## 临近中午：接入你的 Agent

向导为探测到的每家 Agent 打印了 MCP 片段。把你那家的片段贴上（Claude
Code、Codex、ZCode、Kimi、Cursor——每家在 `docs/agents/` 里有逐步指南），
重启该 Agent 的会话，让它搜一次知识库：

```
> 用 nexus 搜一下 "dispatch 超时"
```

只读检索匿名就能用——这是你第一次触到舰队的共享记忆。任何一个 Agent
写回的经验，你的所有 Agent 现在都搜得到。

## 中午：你的第一个派发任务

你（或一个主控 Agent）用 starter-vault 里的模板写任务书——七段：目标、
可验证标准、禁止清单、已排除方案、陷阱地图。然后发到总线：

```bash
curl -s -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to":"my-agent","task_path":"/path/to/task.md","timeout":3600}'
```

执行端立即回 `started`，动手前带凭据搜 MEM，里程碑回 `progress`。
你不用盯着黑屏猜——总线上的 `task_state` 是唯一真相源：

```bash
curl -s "http://127.0.0.1:19998/task_state?limit=5"
```

## 下午：有门禁的工作

Agent 干活时，门禁让它们保持诚实。谁想不交产出就关单，persist 门禁把
任务打回去；两个 Agent 伸向同一个文件，op-log 在 30 秒窗口内拦下第二份
声明。你永远是最高仲裁——机器只是让碰撞可见。

任务完成时，五层资产沉入你的 vault：任务书、全过程日志、带证据的报告、
数据文件，以及一页写清「没做什么、为什么」的否定层。执行者把有价值的
教训写回 MEM，认知诚实闭环从此开始追踪这些教训下次到底管不管用。

## 傍晚：日志

用五段会话日志（模板已附）收这一天：概况、过程、产出、教训、未决。
悬着的问题进决策日志——明天从事实出发，不从记忆出发。

这就是这一天。还是你原来那些 Agent、那个 Markdown 仓库——但从现在起，
任务派发有台账，知识沉淀不蒸发，规则由机器执行，每个完成的任务都留下
不必重来一遍的全部。

## 接下来读什么

- `quickref.md`——三个门禁时刻一页纸
- `protocols.md`——派发/落盘/在场细述
- `docs/agents/`——你那家 Agent 的逐步接入指南
- `README.md`——完整能力巡览
