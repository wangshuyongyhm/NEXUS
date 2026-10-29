"""nexusos_common.lint — 私路径扫描器（拆单1 交付物：工具+基线报告）。

用法：
    python -m nexusos_common.lint <目录>...            # 基线报告（exit 0）
    python -m nexusos_common.lint <目录>... --strict   # CI 模式（命中 exit 1）
    python -m nexusos_common.lint <目录>... --format text

模式数据单源=lint_patterns.PATTERNS（后续新增私路径只改数据文件）。
本工具是后续拆单的「验收武器」：基线命中数对账 audit §1，清零属后续单。
"""
from __future__ import annotations

import sys
from pathlib import Path

from nexusos_common.lint_patterns import ALLOWLIST, PATTERNS, SKIP_DIRS, SOURCE_SUFFIXES

Hit = dict  # {pattern, basis, file, line, text}


def _iter_sources(root: Path):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        # 跳过判定只看 scan root 之内的路径段——绝对路径前缀（如 /.wt/1957/）
        # 不是构建产物，不能当跳过依据（1957 实测：worktree 内全被误跳）
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        yield path


def _allowed(pattern_id: str, file_path: Path) -> bool:
    posix = file_path.as_posix()
    for pid, rx, _basis in ALLOWLIST:
        if pid == pattern_id and rx.search(posix):
            return True
    return False


def scan_path(root: Path) -> list[Hit]:
    """扫描一个根（目录或单文件），返回命中列表（已排序、已放行）。"""
    hits: list[Hit] = []
    for src in _iter_sources(root):
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pid, rx, basis in PATTERNS:
                if rx.search(line) and not _allowed(pid, src):
                    hits.append(
                        {"pattern": pid, "basis": basis, "file": str(src),
                         "line": lineno, "text": line.strip()[:160]}
                    )
    return hits


def report_md(roots: list[Path], hits: list[Hit]) -> str:
    by_pattern: dict[str, list[Hit]] = {}
    for h in hits:
        by_pattern.setdefault(h["pattern"], []).append(h)
    lines = [
        "# 私路径 lint 基线报告",
        "",
        f"- 扫描根：{'、'.join(str(r) for r in roots)}",
        f"- 命中总数：**{len(hits)}**（pattern {len(by_pattern)} 类）",
        "- 口径：audit §1/§3 清单化正则；放行表见 lint_patterns.ALLOWLIST",
        "",
        "| pattern | 依据 | 命中数 |",
        "|---|---|---|",
    ]
    for pid in sorted(by_pattern):
        sample = by_pattern[pid][0]
        lines.append(f"| {pid} | {sample['basis']} | {len(by_pattern[pid])} |")
    lines.append("")
    for pid in sorted(by_pattern):
        lines.append(f"## {pid}")
        lines.append("")
        for h in by_pattern[pid]:
            lines.append(f"- `{h['file']}:{h['line']}` {h['text']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    fmt = "md"
    if "--format" in argv:
        i = argv.index("--format")
        fmt = argv[i + 1]
        del argv[i : i + 2]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    roots = [Path(a).resolve() for a in argv]
    hits: list[Hit] = []
    for r in roots:
        hits.extend(scan_path(r))
    if fmt == "text":
        for h in hits:
            print(f"{h['pattern']}\t{h['file']}:{h['line']}\t{h['text']}")
    else:
        print(report_md(roots, hits))
    if strict and hits:
        print(f"❌ 私路径 lint 命中 {len(hits)} 处（--strict）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
