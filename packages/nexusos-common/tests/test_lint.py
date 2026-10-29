"""nexusos_common.lint 单测：命中/放行/strict 退出码/跳过目录。"""

from nexusos_common import lint
from nexusos_common.lint_patterns import PATTERNS


def test_patterns_present():
    ids = {pid for pid, _rx, _b in PATTERNS}
    assert {"hermes-home", "cursor-home", "os-trash", "tmp-nexus-hardcode",
            "abs-volumes", "abs-users", "parents-derivation",
            "quoted-hermes", "quoted-trash", "vault-layout-literal",
            "quoted-vault-layout"} <= ids


def test_composed_form_patterns(tmp_path):
    """组合形态（1957 实测补）：Path.home()/'frag' 拼接与 vault 布局片段。"""
    src = tmp_path / "composed.py"
    src.write_text(
        "S = Path.home() / '.hermes' / 'scripts'\n"
        "T = home / '.Trash'\n"
        "U = root / '05-System' / '自动化脚本' / 'pool.sh'\n"
        "V = '05-System/自动化脚本/e2e-suite/run-suite.sh'\n",
        encoding="utf-8",
    )
    pids = {h["pattern"] for h in lint.scan_path(src)}
    assert "quoted-hermes" in pids
    assert "quoted-trash" in pids
    assert "quoted-vault-layout" in pids
    assert "vault-layout-literal" in pids


def test_scan_hits_each_pattern(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text(
        "A = '~/Documents'\n"  # 负例：非私路径
        "B = Path.home() / '.hermes' / 'x'\n"  # 负例：拆开写不构成 ~/ 字面量（已知盲区，正则口径）
        "C = expanduser('~/.cursor')\n"
        "D = expanduser('~/.Trash')\n"
        "E = open('/tmp/nexus_loop_goal.txt')\n"
        "F = '/Volumes/Work/x'\n"
        "G = Path(__file__).parents[7]\n"
        "H = expanduser('~/.hermes/scripts')\n",
        encoding="utf-8",
    )
    hits = lint.scan_path(src)
    pids = {h["pattern"] for h in hits}
    assert "cursor-home" in pids
    assert "os-trash" in pids
    assert "tmp-nexus-hardcode" in pids
    assert "abs-volumes" in pids
    assert "parents-derivation" in pids
    assert "hermes-home" in pids  # 行8 ~ /\.hermes
    assert not any(h["line"] == 1 for h in hits)  # 行1 干净


def test_allowlist_anchors_parents(tmp_path):
    """anchors.py 的 parents[N] 哨兵=单源合法用途，放行。"""
    fake = tmp_path / "src" / "nexusos_common" / "anchors.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("x = Path(__file__).parents[4]\n", encoding="utf-8")
    hits = lint.scan_path(fake)
    assert hits == []


def test_allowlist_not_for_other_files(tmp_path):
    other = tmp_path / "src" / "some_pkg" / "deriver.py"
    other.parent.mkdir(parents=True)
    other.write_text("x = Path(__file__).parents[7]\n", encoding="utf-8")
    hits = lint.scan_path(other)
    assert [h["pattern"] for h in hits] == ["parents-derivation"]


def test_skip_dirs(tmp_path):
    (tmp_path / "build" / "gen.py").parent.mkdir()
    (tmp_path / "build" / "gen.py").write_text("P = '/Volumes/x'\n", encoding="utf-8")
    assert lint.scan_path(tmp_path) == []


def test_skip_only_inside_root(tmp_path):
    """回归（1957 实测）：scan root 自身位于 .wt/ 等目录下时不得整体误跳。"""
    inside = tmp_path / ".wt" / "1957" / "pkg"
    inside.mkdir(parents=True)
    src = inside / "a.py"
    src.write_text("P = '/Volumes/x'\n", encoding="utf-8")
    hits = lint.scan_path(inside)  # root=.wt/…/pkg：skip 只看 root 内段
    assert [h["pattern"] for h in hits] == ["abs-volumes"]


def test_strict_exit_code(tmp_path, capsys):
    src = tmp_path / "a.py"
    src.write_text("P = '/Users/wang/x'\n", encoding="utf-8")
    assert lint.main([str(src), "--strict", "--format", "text"]) == 1
    assert lint.main([str(src), "--format", "text"]) == 0  # 基线模式恒 0
    assert lint.main([]) == 2  # 无参数


def test_report_md_contains_summary(tmp_path, capsys):
    src = tmp_path / "b.py"
    src.write_text("Q = '~/Documents'\nR = expanduser('~/.config/nexus/keys')\n", encoding="utf-8")
    lint.main([str(src)])
    out = capsys.readouterr().out
    assert "私路径 lint 基线报告" in out
    assert "config-nexus-home" in out
