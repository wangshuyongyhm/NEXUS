#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pool_write_channel.py — 未决问题池统一写通道（#723 缺陷②，Task 2611110941）。

与 pool-safe-write.sh 同一机制的 Python 共享单元（锁 + 写后校验 + 写痕）：
  - mkdir 自旋锁 .pool-write.lockdir（与 shell 封装同名同目录 → 两路写者互斥互通）；
  - 写后按 wc -l 口径读回校验行数（append=旧+新，replace=新）；
  - 写痕追加 ~/.pool-write.log（P19 对账依赖，格式与 shell 封装逐字段一致）。

为什么不 subprocess 调 shell 封装：销账是「读→改→写」整段原子操作，shell 的
replace 模式无法把「读」纳入锁内（内容在拿锁前就备好），并发下会互吞行（池#102
前科）。故按任务书 §3 修法方向②，把同一锁+写痕机制抽成本共享单元，读和写同锁窗口。
"""
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

LOCKDIR_NAME = ".pool-write.lockdir"        # 与 pool-safe-write.sh 同名锁，互斥互通
TRACE_LOG = Path.home() / ".pool-write.log"  # P19 对账写痕（同 shell 封装）
LOCK_TIMEOUT_S = 5.0                         # 与 shell 封装 17×0.3s≈5s 同量级
SPIN_INTERVAL_S = 0.3

# 2611230964 乙：滚动历史（替换前留底）与环境变量覆盖（路径不写死用户目录）
HISTORY_DIR_ENV = "NEXUS_POOL_HISTORY_DIR"
TRASH_DIR_ENV = "NEXUS_POOL_TRASH_DIR"
HISTORY_KEEP = 100


def pool_history_dir() -> Path:
    """留底目录：环境变量优先，否则 ~/.nexus/xdr/pool-history（池目录之外）。"""
    env = os.environ.get(HISTORY_DIR_ENV, "").strip()
    return Path(env) if env else Path.home() / ".nexus" / "xdr" / "pool-history"


def pool_trash_dir() -> Path:
    """废纸篓目录（超 100 份的旧留底移到这里，不用 rm）。"""
    env = os.environ.get(TRASH_DIR_ENV, "").strip()
    return Path(env) if env else Path.home() / ".Trash"


def vault_root_for_history() -> "Path | None":
    """Vault 根求法（2611230965 甲 → 2611231127 收紧）。

    2611231127：**只认按本模块位置推导出来的真实 Vault 根**（含 05-System 与
    06-Memory 的那一级），**不看 NEXUS_VAULT_ROOT**——仓库里有 25 个测试与自测会把
    环境变量指到沙盒 Vault，里面的假池因此被当成真池留底，挤占真实历史目录的 100 份
    窗口（主控 11-25 22:17 清掉三份 9 行假池备份）。推导不出来返回 None（调用方退回
    上一单的规则：池在某个 06-Memory 目录下就留底，宁可多留）。

    原实现（环境变量优先）注释保留：
        env = os.environ.get("NEXUS_VAULT_ROOT", "").strip()
        if env:
            return Path(env)
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "05-System").is_dir() and (parent / "06-Memory").is_dir():
            return parent
    # 退化：交给 nexusos_common 的哨兵推导（该函数同样优先 env，故只在 env 未设时用）
    if not os.environ.get("NEXUS_VAULT_ROOT", "").strip():
        try:
            from nexusos_common.anchors import vault_root as _vr
            got = _vr(Path(__file__))
            if got:
                return Path(got)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "[2611231127] vault_root 推导失败，退回上一单规则: %s", e)
    return None


def _pool_in_vault(pool: Path) -> bool:
    """池是否在 <Vault 根>/06-Memory/ 之下（真假判定：路径层，不看文件名）。"""
    root = vault_root_for_history()
    if root is None:
        # Vault 根求不出来：池在任一 06-Memory 目录下就照旧留底（宁可多留）
        return "06-Memory" in pool.resolve().parts
    try:
        pool.resolve().relative_to(Path(root).resolve() / "06-Memory")
        return True
    except ValueError:
        return False


def _prune_history(hist: Path) -> list:
    """只保留最近 HISTORY_KEEP 份；超出的按 mtime 最旧优先移进废纸篓目录。"""
    files = sorted(hist.glob("*.md"), key=lambda p: (p.stat().st_mtime, p.name))
    excess = max(0, len(files) - HISTORY_KEEP)
    moved = []
    if excess:
        trash = pool_trash_dir()
        trash.mkdir(parents=True, exist_ok=True)
        for old in files[:excess]:
            os.replace(old, trash / old.name)
            moved.append(old.name)
    return moved


def archive_pool_before_replace(pool: Path, source: str = "python") -> "Path | None":
    """2611230964 乙：替换前把池现有内容留一份到滚动历史目录。

    两个通道（shell 封装与 Python 通道）都调本函数，避免两套留底逻辑各走各的。
    留底失败 → 抛 PoolWriteConflict（调用方据此中止替换，不写一个字节）。

    2611230965 甲：没有显式指定历史目录（NEXUS_POOL_HISTORY_DIR）时，只给 Vault 里的
    真池留底；其它路径的池跳过、返回 None（测试假池不再混进真实历史目录，池#1321 补刀）。
    """
    if not os.environ.get(HISTORY_DIR_ENV, "").strip() and not _pool_in_vault(pool):
        return None  # 跳过留底（调用方照常替换）；写痕行尾记 hist=skipped
    hist = pool_history_dir()
    try:
        hist.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        dest = hist / f"{pool.stem}-{ts}-{source}-{os.getpid()}.md"
        shutil.copy2(pool, dest)  # 内容 = 替换前的池；mtime 一并保留便于对账
        _prune_history(hist)
        return dest
    except Exception as e:
        raise PoolWriteConflict(f"替换前留底失败，替换已中止: {type(e).__name__}: {e}")


class PoolWriteConflict(RuntimeError):
    """池写锁超时或写后校验失败——调用方 fail-open 处置，不静默等待。"""


@contextmanager
def pool_write_lock(pool: Path, timeout_s: float = LOCK_TIMEOUT_S):
    """拿池写锁（mkdir 自旋，同 pool-safe-write.sh）。

    yield 前锁已到手；退出时只删自己 mkdir 成功的那个锁目录；
    超时抛 PoolWriteConflict（对应 shell 封装 exit 3 的 5s 冲突语义）。
    """
    lockdir = pool.parent / LOCKDIR_NAME
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            lockdir.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise PoolWriteConflict(
                    f"池写锁 {timeout_s}s 超时（{lockdir} 被另一写入方持有）")
            time.sleep(SPIN_INTERVAL_S)  # c2-allow: mkdir 自旋锁退避，对齐 pool-safe-write.sh 的 sleep 0.3 同款语义（非绕过型等待）
    try:
        yield lockdir
    finally:
        lockdir.rmdir()  # 只删自己创建的目录；进程被 kill 时与 shell 封装同款残留风险


def _line_count(text: str) -> int:
    """wc -l 口径：数换行符（尾行无换行不计），保证与 shell 封装校验一致。"""
    return text.count("\n")


def _append_trace(op: str, pool: Path, old: int, new: int, back: int, extra: str = ""):
    """写痕落 ~/.pool-write.log——P19 靠「当日日期前缀」对账，格式须与 shell 封装一致。

    2611230964 丙：替换时在行尾多记一项（留底文件名 / 内容时间），既有字段顺序不变。
    """
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(TRACE_LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts} {op} {pool} old={old} new={new} back={back}{(' ' + extra) if extra else ''}\n")


def commit_write(pool: Path, content: str, op: str, source: str = "python"):
    """在已持锁窗口内落盘 + 行数校验 + 写痕（op: append|replace）。

    append=行级追加（禁全文重写——池 #124 前科）；replace=同目录临时文件 +
    os.replace 原子换入。行数对不上抛 PoolWriteConflict（对应 shell 封装
    exit 4 校验失败语义），写痕只在成功后落。

    2611230964：replace 在换入前先调 archive_pool_before_replace 留底；
    留底失败 → 抛 PoolWriteConflict，池一个字节都不动（source 只进留底文件名，
    调用方签名不变：persist_pool_ledger / p02_hardblock 仍按 3 参数调）。
    """
    if op not in ("append", "replace"):
        raise ValueError(f"op 必须是 append|replace，得到 {op}")
    old_text = pool.read_text(encoding="utf-8") if pool.exists() else ""
    hist_name = ""
    if op == "append":
        with open(pool, "a", encoding="utf-8") as f:
            f.write(content)
    else:
        _hist_960 = archive_pool_before_replace(pool, source=source)
        hist_name = _hist_960.name if _hist_960 else ""
        fd, tmp = tempfile.mkstemp(dir=str(pool.parent), prefix=".pool-write.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, pool)
    old_n, new_n = _line_count(old_text), _line_count(content)
    back = _line_count(pool.read_text(encoding="utf-8"))
    expect = old_n + new_n if op == "append" else new_n
    if back != expect:
        raise PoolWriteConflict(f"写后行数 {back} != 预期 {expect}（{op} {pool}）")
    _append_trace(op, pool, old_n, new_n, back,
                  extra=(f"hist={hist_name}" if hist_name else
                         ("hist=skipped" if op == "replace" else "")))
