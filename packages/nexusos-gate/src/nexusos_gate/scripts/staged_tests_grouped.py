#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""staged_tests_grouped.py — 代码门禁 C5 的分组跑测试助手（Task 2611231130）。

背景：C5 把暂存区里的测试文件放进**同一次** `pytest` 跑。暂存了两份同名测试文件
（部署位 `nexusos_xdr/etc/hooks/test_state_transition_guard.py` 与包内
`pypi/nexusos-xdr/tests/test_state_transition_guard.py`，内容不同）时，pytest 默认
按「把测试所在目录插进模块搜索路径」的方式导入，两个同名模块撞车 → 收集错误
（`import file mismatch`），每一份单独跑都是过的。主控 11-25 22:50 提交被这一项拦下。

改法：跑之前按**文件名（basename）分组**——同名的分到不同组，每组各跑一次 pytest，
整体结果取各组最差（保持既有「rc=0 或 rc=5(no tests collected) 算过」的口径）。
文件名不重复时只有一组，行为与改前完全一样。

为什么不用 `--import-mode=importlib`：那种导入方式不把测试所在目录插进搜索路径，
依赖「从同目录导入辅助模块」的测试会坏（C5 的工作目录是 Vault 根，不是测试目录）。
本助手只改「怎么分组」，不动 pytest 的导入方式。

输入：stdin 逐行读取暂存的测试文件路径（不按空格分词——路径里有中文与空格）。
输出：`C5: … -> N group(s) by basename`，每组一行组名与 pytest 尾部几行。
退出码：0 全部通过（rc∈{0,5}）；1 有组失败；2 用法错误。
"""
from __future__ import annotations

import subprocess
import sys
from typing import List

TAIL_LINES = 5


def group_by_basename(files: List[str]) -> List[List[str]]:
    """同名分到不同组：贪心地把每个文件放进「第一个还没占同名」的组。

    返回组的顺序稳定（按首次出现），组数 = 出现的最大同名重复数（无重复时恒为 1 组）。
    """
    groups: List[List[str]] = []
    for path in files:
        base = path.rsplit("/", 1)[-1]
        for grp in groups:
            if all(p.rsplit("/", 1)[-1] != base for p in grp):
                grp.append(path)
                break
        else:
            groups.append([path])
    return groups


def main(argv: List[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        print("C5: no test files on stdin, nothing to run")
        return 0
    groups = group_by_basename(files)
    print(f"C5: {len(files)} staged test file(s) -> {len(groups)} group(s) by basename")
    worst = 0
    for idx, grp in enumerate(groups, 1):
        names = ", ".join(p.rsplit("/", 1)[-1] for p in grp)
        print(f"--- group {idx}/{len(groups)} ({len(grp)} file(s)): {names}")
        try:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *grp],
                                  capture_output=True, text=True, timeout=110)
            out = (proc.stdout + proc.stderr).strip().splitlines()
            for line in out[-TAIL_LINES:]:
                print(line)
            rc_note = "OK" if proc.returncode in (0, 5) else "FAIL"
            print(f"--- group {idx} rc={proc.returncode} {rc_note}")
            if proc.returncode not in (0, 5):
                worst = 1
        except subprocess.TimeoutExpired:
            print(f"--- group {idx} 超时（>110s），按失败处理")
            worst = 1
    print(f"C5: groups={len(groups)} result={'FAIL' if worst else 'OK'}")
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
