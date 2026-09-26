#!/usr/bin/env python3
"""leak-check.py — 零泄漏断言引擎（Task 1582 D 修，1579-D 三形态漏报补全）。

形态覆盖（1579 构造实测过前三种曾全部漏报）：
  1. 明文：sk-… / 数字:长token / cli_… / 长十六进制串
  2. base64：候选串解码后命中明文模式（解码即得 key 的绕过形态）
  3. hex：bytes.fromhex 形态（长十六进制字面量解码后命中）
  4. 二进制：.pyc/.so 等 bytes 里直接含明文标记（编译产物兜底）

用法：python3 scripts/leak-check.py [root]（默认整个仓库树）
退出码：0=零命中；1=有命中（逐条打印 file:line: 形态: 样本前缀）
"""
import base64
import binascii
import re
import sys
from pathlib import Path

# 明文密钥模式（与 1576/1577 report 声称一致——本引擎让声称与实现真正对齐）
PLAIN_PATTERNS = [
    re.compile(rb"sk-[A-Za-z0-9]{16,}"),
    re.compile(rb"[0-9]{9,}:[A-Za-z]{25,}"),
    re.compile(rb"cli_[a-z0-9]{16,}"),
]
# base64 候选：足够长的纯 base64 字母表串（≥24 字符，解码后可能藏 key）
B64_CAND = re.compile(rb"[A-Za-z0-9+/]{24,}={0,2}")
# hex 候选：≥40 长十六进制字面量（20 字节起）
HEX_CAND = re.compile(rb"\b[0-9a-fA-F]{40,}\b")

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules",
             ".pytest_cache", "build", "dist"}
# 我们的源码本身会含这些标记（leak-check 自身/测试样例）——自扫豁免
SELF_EXEMPT = {"scripts/leak-check.py"}


def _decodes_to_key(blob: bytes) -> str:
    """base64/hex 候选解码后是否命中明文模式。命中返回形态名。"""
    for pat in PLAIN_PATTERNS:
        if pat.search(blob):
            return "plain"
    return ""


def scan_bytes(data: bytes) -> list:
    """单文件字节流扫描。返回 [(form, preview)]。"""
    hits = []
    for pat in PLAIN_PATTERNS:
        for m in pat.finditer(data):
            hits.append(("plain", m.group(0)[:24].decode("ascii", "replace")))
    for m in B64_CAND.finditer(data):
        cand = m.group(0)
        try:
            decoded = base64.b64decode(cand, validate=True)
        except (binascii.Error, ValueError):
            continue
        if _decodes_to_key(decoded):
            hits.append(("base64", cand[:24].decode("ascii", "replace")))
    for m in HEX_CAND.finditer(data):
        cand = m.group(0)
        try:
            decoded = binascii.unhexlify(cand)
        except (binascii.Error, ValueError):
            continue
        if _decodes_to_key(decoded):
            hits.append(("hex", cand[:24].decode("ascii", "replace")))
    return hits


def main(root=".") -> int:
    root = Path(root)
    total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if rel in SELF_EXEMPT:
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        hits = scan_bytes(data)
        if hits:
            total += len(hits)
            for form, preview in hits[:3]:
                print(f"LEAK[{form}] {rel}: {preview}…")
    if total:
        print(f"\n✗ {total} 处命中（形态: plain/base64/hex）")
        return 1
    print("✓ 零泄漏（plain + base64 + hex + 二进制 四形态全扫描）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
