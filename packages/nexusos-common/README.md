# nexusos-common

NEXUS 四包（nexusos-gate / nexusos-mem / nexusos-xdr / nexusos-common）共享的**锚点解析单源**（1955 design §3）。

## 为什么存在

三包各自解析 `NEXUS_HOME`/vault 根会漂移出多套状态家目录（1955 audit §1 铁证）。
本包是唯一解析点：零三方依赖，核心 `anchors.py` ≤200 行。

## 锚点解析顺序（design §3.1）

- `nexus_home()`：env `NEXUS_HOME`（必须绝对路径，相对/空串=ConfigError）> 默认 `~/.nexus`
- `vault_root(anchor)`：env `NEXUS_VAULT_ROOT` > 包位置哨兵推导（vault 布局）
- `task_root()`：env `NEXUS_TASK_ROOT` > `$NEXUS_HOME/tasks`
- `subpath(*parts)`：`$NEXUS_HOME` 下子路径（八区名见 `ZONES`）
- `expand_env(s)`：`${NEXUS_HOME}` / `${NEXUS_VAULT_ROOT}` 占位展开

## 缺 vault 三态语义（design §3.2 统一规则）

1. env 显式给定 → 直接用（相对路径拒绝）
2. 哨兵推导可得（包部署于 vault 布局）→ 直接用
3. 不可得 → `vault_root()` 返回 `None`；`vault_root(required=True)` 抛
   `ConfigError`（含 remediation 提示）。**废静默占位**：可降级的功能必须由
   调用方 log WARN，必须 vault 的功能必须显式报错。

## 八区常量（design §1.1，layout_version=1）

`ZONES = ("xdr", "secrets", "mem", "tmp", "trash", "gate", "logs", "tasks")`
（secrets/tmp 目录权限 700，见 `SECRET_DIR_MODE` / `TMP_DIR_MODE`）

## 私路径 lint（拆单1 交付物）

```bash
python -m nexusos_common.lint <目录>...            # 基线报告（exit 0）
python -m nexusos_common.lint <目录>... --strict   # CI 模式（命中 exit 1）
```

扫描私路径模式（audit §1 清单化正则，数据单源 `lint_patterns.py`——后续新增私路径只改数据文件）。
