# quickref.md —— 三个门禁时刻（一页速查卡）

> 会话开始时读。每行=做什么+命令。硬部分门禁引擎已把守——这张卡是你的肌肉记忆。
> 路径假设 `$NEXUS_HOME`（默认 `~/.nexus`）与默认端口。

## 场景 0 —— 我是谁（10 秒）

| 你是 | 读 |
|---|---|
| 主控（要派单） | 本卡 + protocols.md §派发 |
| 执行者（被派单） | 本卡 + protocols.md §落盘 |

## 场景 1 —— init（会话启动/重启/失忆恢复）

1. 读本卡 → 确认角色。
2. 注册在场：`POST $XDR/session/register` `{agent, role, session_id, current_task}`
3. 看谁在线：`GET $XDR/session/active`
4. 服务健康：六端口 11436/11438/11537/19998/4001/19900 的 `/health`
   （init 门禁机械查其中两个：总线与 MEM；其余自查）
5. 过 init 门禁：`gate_check(scenario="init", context={agent, role, session_id})`
6. 向人类（或你的主控）报告就绪。

```bash
curl -s -X POST "$NEXUS_XDR_URL/session/register" -H "Content-Type: application/json" \
  -d '{"agent":"<名字>","role":"executor","session_id":"<名字>-<MMDDHHmm>","status":"init"}'
curl -s "$NEXUS_XDR_URL/session/active"
```

## 场景 2 —— dispatch（派发）

**主控派前：**

1. 目标执行者在线？（presence 在线列表）
2. 并行冲突扫：同文件 120 秒内的 op-log 声明
3. 写任务书（task-spec.md 七段）+ references 带真实内容
4. 总线登记：`POST /dispatch {to, task_path, caller, timeout}`——`caller`
   写你的名字，台账才不失真——同一轮里开始等回调
   （不要盲目轮询）
5. 先过 dispatch 门禁：`gate_check(scenario="dispatch", ...)`

**执行者接单：**

1. 读任务书副本 → 校验凭据（缺凭据=拒绝，回问）
2. 立即回调 `started`（你沉默总线会重投）
3. 动手前带凭据搜 MEM
4. 干活 → 里程碑回调 `progress` → 落盘 → `done`

## 场景 3 —— persist（关单）

**执行者 done 前：**

1. `output/report.md` 带证据 + 机读尾块
2. `process/` 日志 + `output/files/` 非空 + `negative-results.md`
3. `files[]` 里每个路径都在盘上真实存在（验证，不虚报）
4. 高价值发现写回 MEM
5. 才回调 `done`

**主控收口：**

1. 读完每条 done 摘要；ack 复述要点
2. 抽查 `files[]` 落盘
3. 经验回流 MEM 与自己的档案
4. 最终 commit 前 `gate_check(scenario="persist", ...)`

## 默认值

- 调度总线：`http://127.0.0.1:19998` · 知识库：`http://127.0.0.1:11537`
- `$NEXUS_HOME` 默认 `~/.nexus`（配置/日志/数据/密钥都在里面）
- 拿不准时：先搜 MEM，再读专题文档，最后问人类。
