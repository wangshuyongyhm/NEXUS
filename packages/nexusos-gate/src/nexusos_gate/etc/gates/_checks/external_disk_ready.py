"""I8 external_disk_ready — 外接盘依赖 gate（Task1951 G4）.

读 etc/gates/data/external-disk-paths.yaml：
- volume_mount 挂载判定（ismount 或目录存在双通道）
- required 路径逐个存在+可写探针
- optional 缺失只注记；vault_local 不可写=fail
数据文件缺失/解析失败 → WARN（fail-open 注明），不 REJECT 未配置场景。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "external-disk-paths.yaml"


def _writable(p: str) -> bool:
    try:
        fd, tmp = tempfile.mkstemp(dir=p, prefix=".i8probe-", suffix=".tmp")
        os.close(fd)
        os.unlink(tmp)
        return True
    except OSError:
        return False


def check(params, context, agent):
    if not DATA_FILE.exists():
        return True, "I8: 数据文件缺失（%s）——未配置外接盘依赖，fail-open" % DATA_FILE.name
    try:
        data = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return True, "I8: 数据文件解析失败（%s）——fail-open" % e

    mount = data.get("volume_mount", "")
    paths = data.get("paths", {}) or {}
    notes, fails = [], []

    if mount:
        mounted = os.path.ismount(mount) or os.path.isdir(mount)
        if not mounted:
            fails.append("外接盘未挂载: %s" % mount)
        else:
            notes.append("挂载 OK: %s" % mount)

    for p in paths.get("required", []) or []:
        if not os.path.isdir(p):
            fails.append("required 缺失: %s" % p)
        elif not _writable(p):
            fails.append("required 不可写: %s" % p)
        else:
            notes.append("required OK: %s" % p)

    opt_missing = [p for p in (paths.get("optional", []) or []) if not os.path.isdir(p)]
    if opt_missing:
        notes.append("optional 未启用(%d): %s" % (len(opt_missing), ",".join(opt_missing)))

    for p in paths.get("vault_local", []) or []:
        if not os.path.isdir(p) or not _writable(p):
            fails.append("vault_local 不可写: %s" % p)
        else:
            notes.append("vault_local OK: %s" % p)

    detail = "I8 外接盘依赖: " + ("; ".join(fails) if fails else "; ".join(notes) or "无配置项")
    return (not fails), detail
