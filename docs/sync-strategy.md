# NEXUS 主仓 → 公开仓同步机制设计（只设计不实现）

> Task1575 产出。目的：私有主仓（vault 内，含个人数据/密钥历史）→ 公开仓
>（nexus-oss）的长期同步策略，保证公开仓永不含密钥/个人路径/私有数据。

## 1. 分层与流向

```
主仓（<vault>，私有）                公开仓（nexus-oss）
05-System/自动化脚本/pypi/          ──单向──→  packages/{nexus-gatekit,nexus-mem,nexus-xdr}
  nexus-gate → 改名 nexus-gatekit           （import 路径同步改）
05-System/自动化脚本/nexus/（单体包）──拆分──→  packages/*（按服务归属）
db schema：05-System/backups/pg/schema.sql ──过滤──→ db/（去数据只留 DDL）
文档：部署总手册等                      ──翻译/改写──→ docs/（英文为主）
❌ 永不流出：task/、06-Memory/、03-Daily/、04-媒资/、
   .obsidian/、*keys*、.env、nexus-gateway/keys.json、
   含个人 IP/路径/账号的任何文件
```

## 2. 同步管道（三道闸）

1. **白名单拷贝**：只拷贝 `pypi/` 三包 + 显式列名的脚本。拷贝清单（manifest）
   显式枚举文件，不用目录通配——新增文件默认不同步。
2. **脱敏转换层**（`tools/sync-scrub.py`——Task1583 已落地最小实现：内容级密钥/个人痕迹模式扫描，命中即阻断；CI 复检留 TODO）：
   - 路径替换：`<VAULT_ROOT>/...` → `$NEXUS_VAULT_ROOT` 占位、`~` → `~`
   - 密钥模式拦截：`sk-`、`password`、`token`、`BEGIN.*PRIVATE`、公网 IP 正则
     → 命中即拒同步该文件并告警（宁可漏同步不可漏脱敏）
   - 中文逻辑锚点处理：交互/门禁类中文关键词检查在公开仓默认裁剪
     （1558 结论：裁剪非翻译）
3. **CI 复检**：公开仓侧 CI 跑 `grep -R` 密钥/IP/个人路径模式 = 零命中才绿。

## 3. 版本节奏

- 主仓 feat 任务合 main → 人工触发同步（先手动，跑稳后再考虑 nightly）
- 公开仓语义化版本：三包容版本号从主仓 pyproject 取，发布前人工 review diff
- 命名映射单源：`sync-manifest.yaml` 记录 主仓路径→公开仓路径+包名映射
  （nexus-gate→nexus-gatekit 等），改名只改 manifest

## 4. 密钥事故的结构性防线

- 公开仓 `.gitignore` 预置：`*keys*`、`*.env`、`*.pem`、`secrets*`
- pre-commit（公开仓侧）：密钥模式 REJECT（复用 gatekit 自身能力，吃自己的狗粮）
- 主仓侧 1558 审计清单（keys.json/MEM 快照/task 密钥）是"已泄露"集合——
  那些文件在 manifest 里永久黑名单，即使脱敏后也不同步（轮换后亦然）

## 5. 已知待决

- 公开仓 remote 建立与首次 push：等用户确认（发布门禁）
- nexus-mem 的 `config` symlink（主仓 wheel 断点）在公开仓改为真实包内目录
- e2e 测试集：主仓 task/ 下的验证脚本筛选可公开子集迁入 `e2e/`
