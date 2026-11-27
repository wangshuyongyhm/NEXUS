# -*- coding: utf-8 -*-
"""凭据号脱敏（Task 2611269956）：一个函数、一个占位，写入前把 `cred_xxxx` 换成占位。

为什么在写入侧做：检索侧做的话，库里的正文仍然带凭据号；知识库对全体 Agent 可检索，
一条经验写进来之后 24 小时内里面的凭据号是活的。
为什么要替换而不是拒收：拒收会让执行者写经验失败、经验就丢了（api_server 里那套 400
拦截针对的是 sk-/AKIA 这类真名字段，本模块只处理 NEXUS 自己的 cred_ 形态）。
"""
from __future__ import annotations

import re

# 与主控统计口径一致：cred_ 后至少 8 个字母数字
CREDENTIAL_PATTERN = re.compile(r"cred_[A-Za-z0-9]{8,}")
# 占位本身不匹配上面的样式（`[` 不在字符类里），所以重复脱敏是幂等的
CREDENTIAL_PLACEHOLDER = "cred_[已抹去]"


def redact_credentials(text, placeholder: str = None):
    """把正文里的凭据号换成固定占位。返回 (新正文, 替换处数)；空输入原样返回。"""
    if not text:
        return text, 0
    return CREDENTIAL_PATTERN.subn(placeholder or CREDENTIAL_PLACEHOLDER, text)


def redact_text(text) -> str:
    """只要正文的薄封装（切片入库这类只关心结果的调用方用）。"""
    return redact_credentials(text)[0]


def strip_credentials(text) -> str:
    """去掉（而不是替换）凭据号——用于验证「去掉匹配段后逐字节相同」。"""
    if not text:
        return text or ""
    return CREDENTIAL_PATTERN.sub("", text)
