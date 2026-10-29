"""nexusos_common.lint_patterns — 私路径 lint 数据单源（拆单1，audit §1 清单化）。

后续新增私路径模式**只改本文件**（任务书陷阱3）：PATTERNS 加一行 + ALLOWLIST
按需放行。每条 pattern 附依据锚（audit §1 行号 / design §3.3 约束）。
"""
from __future__ import annotations

import re

# (pattern_id, 正则, 依据) —— 编译后的规则列表由 lint.py 消费
# 两类形态：字面量（~/... 或 /abs/...）与组合形态（Path.home() / ".hermes" 式的字符串片段）
_PATTERN_DEFS: tuple[tuple[str, str, str], ...] = (
    ("hermes-home", r"~/\.hermes", "audit §1 行1-7（xdr 状态层写死 hermes）"),
    ("cursor-home", r"~/\.cursor", "audit §1 行9（Cursor 专属假设）"),
    ("os-trash", r"~/\.Trash", "audit §1 行8（macOS 专属，Linux 必炸）"),
    ("config-nexus-home", r"~/\.config/nexus", "audit §3（~/.config/nexus 散落点）"),
    ("tmp-nexus-hardcode", r"/tmp/nexus[-_]", "audit §1 行10（/tmp 硬编码无 TMPDIR 参数化）"),
    ("abs-volumes", r"/Volumes/", "design §3.3（禁硬编码绝对路径）"),
    ("abs-users", r"/Users/", "design §3.3（禁硬编码绝对路径）"),
    ("parents-derivation", r"\.parents\[\d+\]", "design §3.3（禁 parents[N] 布局推导）"),
    # ── 组合形态（1957 基线实测：字面量正则漏掉 audit §1 的 Path.home()/"frag" 拼接） ──
    ("quoted-hermes", r"[\"']\.hermes", "audit §1 行1-7 组合形态（如 Path.home()/'.hermes'）"),
    ("quoted-cursor", r"[\"']\.cursor", "audit §1 行9 组合形态"),
    ("quoted-trash", r"[\"']\.Trash[\"']", "audit §1 行8 组合形态"),
    ("quoted-config-nexus", r"[\"']\.config[/\\]nexus", "audit §3 组合形态"),
    ("vault-layout-literal", r"05-System[/\\]自动化脚本", "audit §1 行11-12（vault 相对路径假设）"),
    ("quoted-vault-layout", r"[\"']05-System[\"']", "audit §1/§5（vault 布局字符串片段假设）"),
)

# 放行表：(pattern_id, 路径后缀正则) —— 命中则不计入。放行必须写理由。
# 锚点哨兵推导是 parents[N] 的唯一合法用途（design §3.2 单源即本包 anchors.py）。
_ALLOWLIST_DEFS: tuple[tuple[str, str, str], ...] = (
    ("parents-derivation", r"nexusos_common[/\\]anchors\.py$", "锚点哨兵推导单源"),
    # lint 自身文件含 pattern 字面量/片段（自指误报）——全部 pattern 统一放行
    ("hermes-home", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("cursor-home", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("os-trash", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("config-nexus-home", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("tmp-nexus-hardcode", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("abs-volumes", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("abs-users", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("parents-derivation", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("quoted-hermes", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("quoted-cursor", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("quoted-trash", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("quoted-config-nexus", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("vault-layout-literal", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("quoted-vault-layout", r"nexusos_common[/\\]lint_patterns\.py$", "lint 数据自指"),
    ("hermes-home", r"nexusos_common[/\\]lint\.py$", "lint 自指"),
)

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (pid, re.compile(rx), basis) for pid, rx, basis in _PATTERN_DEFS
)

ALLOWLIST: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (pid, re.compile(rx), basis) for pid, rx, basis in _ALLOWLIST_DEFS
)

# 扫描的源码后缀（design §3.3「包源码」；.md 文档面另由 doc 审查覆盖）
SOURCE_SUFFIXES = (".py", ".sh", ".yaml", ".yml", ".toml")

# 跳过的目录名（构建产物/缓存/VCS——非源码）
SKIP_DIRS = {"build", "dist", "dist-repos", "__pycache__", ".git", ".wt", ".venv",
             ".pytest_cache", ".ruff_cache", "node_modules", ".nexus"}
