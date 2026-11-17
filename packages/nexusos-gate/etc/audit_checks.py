#!/usr/bin/env python3
"""audit_checks.py — Task816 审计 gate 自研检查（ruff 覆盖不了的语义层）

子命令：
  observability <project_root>   C15：staged diff 里新增 except 块必须有 log
                                 （logger.warning/error/exception/critical/info）或
                                 显式 `# silent: 理由` 声明；仅 logger.debug=吞错命中；
                                 裸 return/continue/break 出 except 块无 log 也命中
  contract <project_root>        C16：diff 触及 Redis 键读写/API 路由 → 提醒跨端契约
                                 须附写读双方对齐证据（自动判不了语义，强制提醒降级）

设计原则（README 诚实边界同款）：不求完美求有。grep 级启发式，误报可 WARN 容忍
（C14-C16 全部 WARN 起步，跑稳 2 轮再评估升 REJECT）。
"""
import re
import subprocess
import sys

LOG_RE = re.compile(r"logger\.(warning|error|exception|critical|info)\(")
DEBUG_RE = re.compile(r"logger\.debug\(")
SILENT_RE = re.compile(r"#\s*silent:")
EXCEPT_RE = re.compile(r"^\+\s*(except\b|}\s*catch)")   # py 为主，顺手覆盖 js 形态
ADDED_RE = re.compile(r"^\+")
HUNK_RE = re.compile(r"^@@")

CONTRACT_RE = re.compile(
    r"(_r_set|_r_get|\.setex\(|SMEMBERS|@router\.|include_router|ws_channel_|"
    r"latest_positions|qmt765:|publish\()"
)


def _staged_diff(root: str) -> str:
    # Task1552 S2: quotepath=off——中文路径八进制转义致 grep '\.py$' 漏检（1545 实证）
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--cached", "-U8", "--", "*.py"],
        cwd=root, capture_output=True, text=True,
    ).stdout


def observability(root: str) -> int:
    """except 块可观测性。返回命中数（0=通过）。"""
    diff = _staged_diff(root)
    hits = []
    in_block = False
    block: list[str] = []
    block_file = ""
    cur_file = ""

    def flush():
        if not in_block or not block:
            return
        body = "\n".join(block)
        if LOG_RE.search(body) or SILENT_RE.search(body):
            return
        kind = "debug 级吞错" if DEBUG_RE.search(body) else "except 块无日志"
        first = block[0].strip()[:80]
        hits.append(f"{block_file}: {kind}: {first}")

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
        if EXCEPT_RE.match(line):
            flush()
            in_block = True
            block = [line[1:]]
            block_file = cur_file
            continue
        if in_block:
            if HUNK_RE.match(line) or line.startswith("+++ "):
                flush()
                in_block = False
                block = []
            elif ADDED_RE.match(line):
                block.append(line[1:])
                # except 块最多看 8 行新增（超了算块外）
                if len(block) > 8:
                    flush()
                    in_block = False
                    block = []
            elif line.startswith("-"):
                continue
            else:
                # 上下文行（未改动）也算块内证据——既有 log 调用在上下文里同样有效
                block.append(line)
                if len(block) > 8:
                    flush()
                    in_block = False
                    block = []
    flush()

    for h in hits:
        print(f"⚠️ {h}")
    if hits:
        print(f"C15 命中 {len(hits)} 处（except 块必须有 logger.warning/error/exception 或 `# silent: 理由` 声明）")
        return 1
    print("C15 可观测性检查通过（staged 新增 except 块均有日志/静默声明）")
    return 0


def contract(root: str) -> int:
    """跨端契约改动提醒。命中即 WARN（强制提醒，不判语义）。"""
    # Task1552 S2: quotepath=off（同 _staged_diff，防中文路径显示层乱码）
    diff = subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--cached", "-U0"],
        cwd=root, capture_output=True, text=True,
    ).stdout
    added = [l for l in diff.splitlines() if ADDED_RE.match(l) and not l.startswith("+++")]
    hits = sorted({m.group(0) for l in added for m in [CONTRACT_RE.search(l)] if m})
    if hits:
        print(f"⚠️ 跨端契约改动（命中：{'、'.join(hits[:6])}）——任务书须附写读双方对齐证据"
              "（今晚 12 断链全是这类：键格式/TTL/枚举/字段名四模式）")
        return 1
    print("C16 无跨端契约改动信号")
    return 0


def comment_audit(root: str) -> int:
    """C18: §7.7 三查——①diff 触及 def/class 无 docstring（ast 工作区法,删文件跳过）
    ②新增 # 注释纯 ASCII 疑似英文模板 ③连续≥3 行 # 呈代码特征=注释掉的代码。WARN 非禁止。"""
    import ast, os
    diff = _staged_diff(root)
    hits, defs, zh_missing, run = [], [], {}, []
    cur = ""
    CODEISH = re.compile(r"[=(]|import |return |:$")  # 代码特征: 赋值/调用/import/return/行尾:
    # 排除: shebang / linter 指令(noqa|type:|pylint 等) / URL / 空注释
    SKIP = re.compile(r"^\s*#!|^\s*#\s*(noqa|type:|pylint|mypy|ruff|fmt:|isort:)|https?://|^\s*#\s*$")
    def flush():
        """结算当前注释连跑段：≥3 行且代码特征≥2 → 记一次疑似残渣块。"""
        if len(run) >= 3 and sum(bool(CODEISH.search(c)) for _, c in run) >= 2:
            hits.append(f"{run[0][0]}: 疑似注释掉的代码块（连续 {len(run)} 行含赋值/调用特征——§7.7 残渣清理）")
    lineno = 0
    for i, line in enumerate(diff.splitlines()):
        if line.startswith("+++ b/"):
            cur, _ = line[6:], flush()
            run = []
            continue
        if HUNK_RE.match(line):
            flush(); run = []
            lineno = int(line.split("+", 2)[1].split(",")[0]) - 1  # 新文件侧起点-1
            continue
        lineno += 1 if line.startswith("+") and not line.startswith("+++") else 0
        m = re.match(r"^\+\s*(?:async\s+)?(?:def|class)\s+(\w+)", line)
        if m:
            # ast 工作区法+行号对齐：按名匹配会撞同名函数（自审实证 C15 老 flush）——
            # 记录 def 行号，ast 节点 lineno 对齐 ±2 内才认（async/装饰器容差）
            defs.append((cur, m.group(1), lineno, line[1:].strip()[:60]))
        cm = re.match(r"^\+\s*#(.*)$", line)
        if cm:
            run.append((cur, cm.group(1)))
            if not SKIP.search(line[1:]) and not re.search(r"[\u4e00-\u9fff]", cm.group(1)):
                zh_missing[cur] = zh_missing.get(cur, 0) + 1
        else:
            flush(); run = []
    flush()
    seen, uniq = set(), []
    for d in defs:
        if d[:2] not in seen:
            seen.add(d[:2]); uniq.append(d)
    for f, name, dline, src in uniq:
        try:
            tree = ast.parse(open(os.path.join(root, f), encoding="utf-8").read())
        except (OSError, SyntaxError):
            continue  # 文件删除/语法异常——diff 自有其他 gate 兜
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and n.name == name and abs(n.lineno - dline) <= 2 \
                    and not ast.get_docstring(n):
                hits.append(f"{f}:{dline} {src} … 无 docstring（§7.7）")
    for f, n in sorted(zh_missing.items()):
        hits.append(f"{f}: 新增纯 ASCII 注释 {n} 行（疑似英文模板——§7.7 注释用中文白话）")
    for h in hits:
        print(f"⚠️ {h}")
    if hits:
        print(f"C18 命中 {len(hits)} 处（注释审计 WARN：docstring/中文白话/残渣三查）")
        return 1
    print("C18 注释审计通过（新增面三查全过）")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: audit_checks.py <observability|contract|comment> <project_root>")
        sys.exit(2)
    cmd, root = sys.argv[1], sys.argv[2]
    if cmd == "observability":
        sys.exit(observability(root))
    if cmd == "contract":
        sys.exit(contract(root))
    if cmd == "comment":
        sys.exit(comment_audit(root))
    print(f"unknown subcommand: {cmd}")
    sys.exit(2)
