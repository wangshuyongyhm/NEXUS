"""nexusos_common.anchors — NEXUS 四包共享锚点解析（单源，1955 design §3）。

零三方依赖；核心红线 ≤200 行。所有解析在调用时进行（非 import 时）——
多 NEXUS_HOME/测试沙箱可切（design §2.1 env 命名规范）。
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "SECRET_DIR_MODE",
    "TMP_DIR_MODE",
    "VAULT_MISSING_REMEDIATION",
    "ZONES",
    "ConfigError",
    "auto_scripts_dir",
    "expand_env",
    "nexus_home",
    "subpath",
    "task_root",
    "vault_root",
]


class ConfigError(Exception):
    """配置错误——必须携带 remediation 提示（design §3.2「必须则显式报错」）。"""


VAULT_MISSING_REMEDIATION = (
    "修复：export NEXUS_VAULT_ROOT=<vault绝对路径>，"
    "或将包部署于 vault 布局（<vault>/05-System/自动化脚本/pypi/<pkg>/）。"
)

# 八区目录常量（design §1.1 目录树，layout_version=1）
ZONES = ("xdr", "secrets", "mem", "tmp", "trash", "gate", "logs", "tasks")
SECRET_DIR_MODE = 0o700  # secrets/ 含凭据：700（design §1.2）
TMP_DIR_MODE = 0o700     # tmp/ 含 dispatch 临时上下文：700（design §1.2）

# 布局版本轴（design §7）：独立于包 semver 的目录布局版本，目录树破坏性
# 变更时 +1 并随发布提供 nexus migrate；doctor/update 与 .nexus/config.toml
# [meta] layout_version 对账（SUPPORTED_LAYOUTS=本包可消费的布局版本集合）。
LAYOUT_VERSION = 1
SUPPORTED_LAYOUTS = frozenset({1})

# 哨兵目录名：vault 布局的「自动化脚本」层（其下含 nexus/ 子目录）
_SENTINEL_NAME = "自动化脚本"
_SENTINEL_CHILD = "nexus"


def _abs_env(name: str) -> Path | None:
    """读 env 锚点：未设/空白→None；相对路径→ConfigError（拒绝静默展开两套家）。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise ConfigError(
            f"{name}={raw!r} 非绝对路径——相对锚点会随 cwd 静默展开出第二套家目录，显式拒绝。"
            f"请改为绝对路径。"
        )
    return p


def auto_scripts_dir(anchor: Path | None = None, *, max_up: int = 10) -> Path | None:
    """vault 布局哨兵：从 anchor 向上找「自动化脚本/ 且含 nexus/」的父目录。

    非 vault 布局返回 None。anchor 默认=本文件（调用方通常传自己的
    Path(__file__) 以按各自安装位置探测——wheel 装在 site-packages 时
    common 自身位置不代表调用包位置）。
    """
    here = Path(anchor).resolve() if anchor else Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == _SENTINEL_NAME and (parent / _SENTINEL_CHILD).is_dir():
            return parent
        if max_up <= 0:
            break
        max_up -= 1
    return None


def nexus_home() -> Path:
    """NEXUS_HOME 锚点：env（必须绝对）> 默认 ~/.nexus（design §3.1）。"""
    return _abs_env("NEXUS_HOME") or Path.home() / ".nexus"


def vault_root(anchor: Path | None = None, *, required: bool = False) -> Path | None:
    """vault 根解析（design §3.2 三态）。

    顺序：env NEXUS_VAULT_ROOT > anchor 哨兵推导（vault 布局）。
    不可得：required=True → ConfigError（含 remediation）；False → None
    （禁静默：可降级功能调用方必须 log WARN，必须 vault 功能必须显式报错）。
    """
    env = _abs_env("NEXUS_VAULT_ROOT")
    if env is not None:
        return env
    auto = auto_scripts_dir(anchor)
    root = auto.parents[1] if auto is not None else None  # 自动化脚本→05-System→vault 根
    if root is None and required:
        raise ConfigError(
            "vault 不可用（NEXUS_VAULT_ROOT 未设且非 vault 布局）。" + VAULT_MISSING_REMEDIATION
        )
    return root


def task_root() -> Path:
    """调度任务区锚点：env NEXUS_TASK_ROOT > $NEXUS_HOME/tasks（design §6 单抽象）。"""
    return _abs_env("NEXUS_TASK_ROOT") or nexus_home() / "tasks"


def subpath(*parts: str) -> Path:
    """$NEXUS_HOME 下子路径（parts 首段应为 ZONES 区名）。"""
    return nexus_home().joinpath(*parts)


def expand_env(value: str) -> str:
    """${NEXUS_HOME}/${NEXUS_VAULT_ROOT} 占位展开（design §2.1）。

    NEXUS_HOME 恒可解析；vault 不可用时 ${NEXUS_VAULT_ROOT} 保留原样
    （调用方校验——显式留痕优于静默吞掉）。
    """
    out = value.replace("${NEXUS_HOME}", str(nexus_home()))
    vr = vault_root()
    if vr is not None:
        out = out.replace("${NEXUS_VAULT_ROOT}", str(vr))
    return out
