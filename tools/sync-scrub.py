#!/usr/bin/env python3
"""sync-scrub.py — 主仓→公开仓同步的内容级脱敏闸（sync-strategy.md 三道闸之②）。

用法：
  sync-scrub.py <file...>          # 扫描候选流出文件；命中密钥/个人痕迹即阻断
  sync-scrub.py --manifest         # 校验 manifest 白名单内的源文件全部干净

退出码：0=全部干净；1=有命中（清单打印到 stderr）。命中即拒同步该文件——
宁可漏同步，不可漏脱敏（sync-strategy §2）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

OSS_ROOT = Path(__file__).resolve().parent.parent

# 内容级密钥模式（1578 S2 补全五式：AKIA/ghp_/AIza/xoxb/eyJ + 原有）
SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9_-]{8,}", "OpenAI 式 API key (sk-)"),
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key (AKIA)"),
    (r"ghp_[a-zA-Z0-9]{20,}", "GitHub PAT (ghp_)"),
    (r"AIza[a-zA-Z0-9_-]{20,}", "Google API key (AIza)"),
    (r"xox[bapors]-[a-zA-Z0-9-]{10,}", "Slack token (xox*)"),
    (r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}", "JWT (eyJ)"),
    (r"BEGIN [A-Z ]*PRIVATE KEY", "PEM 私钥"),
    (r"(?i)(password|passwd|secret)\s*[:=]\s*['\"]?\S{6,}", "口令键值对"),
    (r"(?i)(token|api[_-]?key)\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{16,}", "token/key 键值对"),
    (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "IP 地址（需人工确认公私）"),
]
# 个人痕迹模式（中性化闸）
PERSONAL_PATTERNS = [
    (r"/Users/[a-zA-Z]+/", "个人 home 路径"),
    (r"/Volumes/[A-Z][a-zA-Z]+/", "个人卷标路径"),
]

# 白名单后缀内豁免（占位文档允许提到模式本身）
DOC_WHITELIST = {"sync-strategy.md", "NOTICE", "sync-scrub.py"}


def scan_file(path: Path) -> list[str]:
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"读取失败: {e}"]
    if path.name in DOC_WHITELIST:
        return []
    for pat, label in SECRET_PATTERNS + PERSONAL_PATTERNS:
        for m in re.finditer(pat, text):
            line = text[: m.start()].count("\n") + 1
            hits.append(f"{label} @L{line}")
    return hits


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--manifest":
        manifest = OSS_ROOT / "sync-manifest.yaml"
        if not manifest.exists():
            print(f"manifest 不存在: {manifest}", file=sys.stderr)
            return 1
        # manifest 里 src: 列出的主仓文件逐个扫（仅在有 MAIN_REPO env 时）
        main_repo = os.environ.get("MAIN_REPO")
        if not main_repo:
            print("manifest 模式需要 MAIN_REPO=<主仓路径>", file=sys.stderr)
            return 2
        targets = []
        for line in manifest.read_text().splitlines():
            m = re.match(r"\s*-?\s*src:\s*(\S+)", line)
            if m:
                targets.append(Path(main_repo) / m.group(1))
        args = [str(t) for t in targets]
    bad = 0
    for a in args:
        p = Path(a)
        hits = scan_file(p)
        if hits:
            bad += 1
            print(f"🔴 {p}:", file=sys.stderr)
            for h in hits:
                print(f"   - {h}", file=sys.stderr)
        else:
            print(f"✅ {p}")
    if bad:
        print(f"\n阻断：{bad} 个文件命中脱敏闸——宁漏同步不漏脱敏", file=sys.stderr)
        return 1
    print("\n全部干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
