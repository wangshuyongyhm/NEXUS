# protocols.md —— 三条线上协议（通用版）

> NEXUS 的协作跑在三条小协议上。每条在这里给出消息形态与实例。
> 全部走普通 HTTP。同一总线也为讲 MCP 的 Agent 暴露一个 MCP 端点（`/mcp`）。

## 1. 派发（dispatch）——经总线的任务分派

总线（`:19998`）是任务分派的唯一通道。主控提交任务书；总线把它登记进
台账（`task_state`——唯一真相源），签发任务绑定凭据，并把任务书投递到
执行者的会话。

**派发：**

```bash
curl -X POST http://127.0.0.1:19998/dispatch \
  -H "Content-Type: application/json" \
  -d '{"to": "<执行者>", "task_path": "/abs/path/task.md", "timeout": 3600}'
```

**回调四态+**（执行者 → 总线，同一通道）：

| 状态 | 时机 | 必填字段 |
|---|---|---|
| `started` | 读完任务书立即 | task_id、source |
| `progress` | 里程碑 | + summary |
| `need_decision` | 卡住，需要人类/主控抉择 | + 带编号选项的问题 |
| `done` | 产出落盘、门禁绿 | + files[]、tests、summary |
| `failed` | 不可恢复 | + error |

```bash
curl -X POST http://127.0.0.1:19998/callback \
  -H "Content-Type: application/json" \
  -d '{"task_id": "<副本里注入的 id>", "source": "<你的名字>",
       "status": "done", "files": ["output/report.md"], "summary": "..."}'
```

**等待：** 主控异步等回调——不轮询截图、不 sleep 死等。总线把每次回调
记进台账；巡逻循环会对沉默的执行端重投任务书，并对超时任务打标。

## 2. 落盘（persist）——五层资产契约

token 买来的推理不可再生，所以每个任务以五层落盘收尾：

```
task/<编号>-<名字>/
├── input/            # 任务书（含派发副本）
├── process/          # 全过程日志
├── output/
│   ├── report.md            # 结论，带机读尾块
│   ├── files/               # 本任务产出的全部数据工件
│   └── negative-results.md  # 被否决的方案，各附原因
└── reproduce.sh      # 一条命令复验全部结论
```

质量门槛：报告带证据（命令+输出，或盘上真实存在的文件路径）；`done` 前
`files[]` 声明逐条验证落盘；否定层写明**没做**什么、为什么。没有产出的
任务不算完成——persist 门禁会打回。

## 3. 在场（presence）——看见整支舰队

Agent 注册、心跳、声明、广播：

```bash
# 注册（会话启动时一次）
curl -X POST http://127.0.0.1:19998/session/register \
  -d '{"agent": "<名字>", "role": "executor", "session_id": "<id>", "status": "init"}'

# 改共享文件前声明意图
curl -X POST http://127.0.0.1:19998/session/op-log \
  -d '{"agent": "<名字>", "op": "edit", "target": "<文件>", "detail": "<改什么>"}'
# → 返回 {"conflict": true} 表示 30 秒窗口内有别的 Agent 声明了同一目标——
#    停下来协调，别硬闯。

# 广播舰队该知道的完成事件
curl -X POST http://127.0.0.1:19998/session/broadcast \
  -d '{"sender": "<名字>", "message": "<什么变了>", "msg_type": "alert"}'
```

在场感知回答舰队时刻在问的问题：谁在线、谁在干什么、刚才有没有人动过
我的文件。内容指纹（hash+mtime+size）识别「声明之后文件被偷改」。
任何冲突，人类永远是最高仲裁者。

## 三条协议如何咬合

派发让工作流动；在场让并行可见；落盘让完成永存。三个门禁
（init/dispatch/persist）守在三条缝上机械执行契约——见 `gates/`。
