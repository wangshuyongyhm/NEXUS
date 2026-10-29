"""nexusos-common 锚点解析单测（拆单1 验收线：解析顺序/八区常量/缺 vault 三态）。"""
import pytest
from nexusos_common import (
    SECRET_DIR_MODE,
    TMP_DIR_MODE,
    VAULT_MISSING_REMEDIATION,
    ZONES,
    ConfigError,
    auto_scripts_dir,
    expand_env,
    nexus_home,
    subpath,
    task_root,
    vault_root,
)

# ── 八区常量 ────────────────────────────────────────────────

def test_zones_eight_members():
    assert ZONES == ("xdr", "secrets", "mem", "tmp", "trash", "gate", "logs", "tasks")


def test_zone_modes():
    assert SECRET_DIR_MODE == 0o700
    assert TMP_DIR_MODE == 0o700


# ── nexus_home 解析顺序 ─────────────────────────────────────

def test_nexus_home_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    assert nexus_home() == tmp_path


def test_nexus_home_default(monkeypatch):
    monkeypatch.delenv("NEXUS_HOME", raising=False)
    assert nexus_home().name == ".nexus"


def test_nexus_home_rejects_relative(monkeypatch):
    monkeypatch.setenv("NEXUS_HOME", "relative/dir")
    with pytest.raises(ConfigError, match="绝对路径"):
        nexus_home()


def test_nexus_home_rejects_empty(monkeypatch):
    monkeypatch.setenv("NEXUS_HOME", "   ")
    assert nexus_home().name == ".nexus"  # 空白=未设，回落默认而非报错


# ── vault_root 三态 ─────────────────────────────────────────

def _make_vault_layout(tmp_path):
    """造 vault 布局哨兵：<vault>/05-System/自动化脚本/nexus/ + 包内探测文件。"""
    auto = tmp_path / "05-System" / "自动化脚本"
    (auto / "nexus").mkdir(parents=True)
    probe = auto / "pypi" / "fake-pkg" / "src" / "fake" / "mod.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("", encoding="utf-8")
    return probe


def test_vault_root_state1_env_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_VAULT_ROOT", str(tmp_path))
    assert vault_root() == tmp_path  # 状态①：env 显式（哨兵不存在也用 env）


def test_vault_root_state1_env_rejects_relative(monkeypatch):
    monkeypatch.setenv("NEXUS_VAULT_ROOT", "rel/vault")
    with pytest.raises(ConfigError):
        vault_root()


def test_vault_root_state2_sentinel_derived(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_VAULT_ROOT", raising=False)
    probe = _make_vault_layout(tmp_path)
    root = vault_root(anchor=probe)  # 状态②：哨兵推导
    assert root == tmp_path


def test_vault_root_state3_missing_none(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_VAULT_ROOT", raising=False)
    orphan = tmp_path / "plain" / "site-packages" / "fake" / "mod.py"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("", encoding="utf-8")
    assert vault_root(anchor=orphan) is None  # 状态③：不可得→None（禁静默占位）


def test_vault_root_state3_required_raises_with_remediation(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_VAULT_ROOT", raising=False)
    orphan = tmp_path / "plain2" / "fake" / "mod.py"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        vault_root(anchor=orphan, required=True)
    assert VAULT_MISSING_REMEDIATION in str(ei.value)  # 报错信息含 remediation


def test_auto_scripts_dir_non_vault_returns_none(tmp_path):
    assert auto_scripts_dir(tmp_path / "nope.py") is None


def test_auto_scripts_dir_deep_anchor(tmp_path):
    """回归（1957 实测）：_checks 插件深度 …/etc/gates/_checks/x.py 也能探到哨兵。"""
    monkeypatch_delenv = None  # noqa: F841 —— 显式走 anchor，不依赖 env
    deep = tmp_path / "05-System" / "自动化脚本" / "pypi" / "nexusos-gate" / "src" / "nexusos_gate" / "etc" / "gates" / "_checks" / "_vault_root.py"
    (tmp_path / "05-System" / "自动化脚本" / "nexus").mkdir(parents=True)
    deep.parent.mkdir(parents=True)
    deep.write_text("", encoding="utf-8")
    assert auto_scripts_dir(deep) == tmp_path / "05-System" / "自动化脚本"
    assert vault_root(anchor=deep) == tmp_path


# ── task_root / subpath / expand_env ────────────────────────

def test_task_root_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_TASK_ROOT", str(tmp_path / "tasks-x"))
    assert task_root() == tmp_path / "tasks-x"


def test_task_root_default_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.delenv("NEXUS_TASK_ROOT", raising=False)
    assert task_root() == tmp_path / "tasks"


def test_subpath_zones(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    assert subpath("secrets", "cred-secret") == tmp_path / "secrets" / "cred-secret"


def test_expand_env_both(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEXUS_VAULT_ROOT", str(tmp_path / "vault"))
    assert expand_env("${NEXUS_HOME}/gate/${NEXUS_VAULT_ROOT}") == (
        str(tmp_path / "home") + "/gate/" + str(tmp_path / "vault")
    )


def test_expand_env_vault_missing_keeps_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NEXUS_VAULT_ROOT", raising=False)
    # common 自身可能部署于 vault 布局（哨兵可推导）——强制哨兵失败模拟真缺 vault
    monkeypatch.setattr("nexusos_common.anchors.auto_scripts_dir",
                        lambda anchor=None, **kw: None)
    out = expand_env("${NEXUS_HOME}/x/${NEXUS_VAULT_ROOT}")
    assert str(tmp_path / "home") in out
    assert "${NEXUS_VAULT_ROOT}" in out  # vault 不可得：留痕不静默吞
