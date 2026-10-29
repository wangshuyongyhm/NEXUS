"""nexusos_common — NEXUS 四包共享锚点解析单源（1955 design §3）。

public API 从 anchors 扁平再导出；lint 子模块独立（拆单1 交付物）。
"""
from nexusos_common.anchors import (
    SECRET_DIR_MODE,
    TMP_DIR_MODE,
    VAULT_MISSING_REMEDIATION,
    ZONES,
    ConfigError,
    auto_scripts_dir,
    expand_env,
    nexus_home,
    subpath,
    task_root,
    vault_root,
)

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

__version__ = "1.0.0"
