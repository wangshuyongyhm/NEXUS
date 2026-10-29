#!/usr/bin/env python3
"""test_update_check.py — 1970 四态实测（新版提示/同版零输出/断网静默/off 不联网）+缓存+比较。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nexusos_common import update_check as uc

# ── 比较与提示行 ────────────────────────────────────────────

def test_ver_compare():
    assert uc.is_newer("1.1.0", "1.0.0") is True
    assert uc.is_newer("1.0.0", "1.0.0") is False
    assert uc.is_newer("v2.0", "1.9.9") is True
    assert uc.is_newer("", "1.0.0") is False
    assert uc.is_newer("1.0.1", "1.0.0a1") is True  # 预发布落后稳态


def test_notify_line_shapes():
    hi = {"update_available": True, "latest": "1.1.0"}
    assert uc.notify_line(hi) == "[nexus] v1.1.0 available → pipx upgrade nexusos-xdr && nexus update"
    assert uc.notify_line({"update_available": False, "latest": "1.0.0"}) is None
    assert uc.notify_line({"update_available": True, "latest": None}) is None


# ── 四态（mock feed via monkeypatch） ───────────────────────

def test_state1_newer_version_prompts(tmp_path, monkeypatch):
    """态1：feed 返回高版本 → 提示行出现（缓存路径隔离）。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "pypi")
    monkeypatch.setattr(uc, "_fetch_latest", lambda f, timeout=uc.FETCH_TIMEOUT: "99.0.0")
    s = uc.get_update_status(allow_fetch=True)
    assert s["update_available"] is True and s["latest"] == "99.0.0"
    assert uc.notify_line(s).startswith("[nexus] v99.0.0")
    # 缓存已写（fetch 成功路径）
    assert json.loads((tmp_path / "cache" / "update-check.json").read_text())["latest"] == "99.0.0"


def test_state2_same_version_zero_output(tmp_path, monkeypatch):
    """态2：同版 → 零输出（notify_line None）。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "pypi")
    monkeypatch.setattr(uc, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(uc, "_fetch_latest", lambda f, timeout=uc.FETCH_TIMEOUT: "1.0.0")
    s = uc.get_update_status(allow_fetch=True)
    assert s["update_available"] is False and uc.notify_line(s) is None


def test_state3_offline_silent(tmp_path, monkeypatch):
    """态3：断网（fetch 抛异常）→ 静默 error 态不炸，旧缓存保留。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "github")
    (tmp_path / "cache").mkdir(parents=True)
    (tmp_path / "cache" / "update-check.json").write_text(
        json.dumps({"feed": "github", "latest": "1.0.0", "checked_at": time.time() - 90000}))
    def boom(feed, timeout=uc.FETCH_TIMEOUT):
        raise OSError("simulated offline")
    monkeypatch.setattr(uc, "_fetch_latest", boom)
    s = uc.get_update_status(allow_fetch=True)
    assert s.get("error") == "fetch-failed" and s["latest"] == "1.0.0"  # 旧缓存兜提示


def test_state4_off_no_network_no_cache_write(tmp_path, monkeypatch):
    """态4：off → 不联网（fetch 断言不被调）+缓存无写入。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.delenv("NEXUS_UPDATE_FEED", raising=False)
    called = []
    monkeypatch.setattr(uc, "_fetch_latest", lambda f, timeout=uc.FETCH_TIMEOUT: called.append(f) or "9.9.9")
    s = uc.get_update_status(allow_fetch=True)
    assert s["feed"] == "off" and not called
    assert not (tmp_path / "cache" / "update-check.json").exists()


# ── 24h 缓存 ───────────────────────────────────────────────

def test_cache_fresh_no_refetch(tmp_path, monkeypatch):
    """缓存 24h 内 → 二次获取零网络（fetch 不被调）。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "pypi")
    (tmp_path / "cache").mkdir(parents=True)
    (tmp_path / "cache" / "update-check.json").write_text(
        json.dumps({"feed": "pypi", "latest": "5.0.0", "checked_at": time.time() - 100}))
    called = []
    monkeypatch.setattr(uc, "_fetch_latest", lambda f, timeout=uc.FETCH_TIMEOUT: called.append(f) or "x")
    s = uc.get_update_status(allow_fetch=True)
    assert not called and s["from_cache"] is True and s["latest"] == "5.0.0"


def test_cli_entry_exempt_and_json(tmp_path, monkeypatch, capsys):
    """CLI 入口：init/doctor/update 豁免 + --json/--no-check 抑制。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "pypi")
    (tmp_path / "cache").mkdir(parents=True)
    (tmp_path / "cache" / "update-check.json").write_text(
        json.dumps({"feed": "pypi", "latest": "9.9.9", "checked_at": time.time()}))
    for argv in (["init"], ["doctor"], ["--json", "anything"], ["--no-check", "x"]):
        uc.cli_notify(argv)
        assert capsys.readouterr().err == ""  # 豁免/抑制零输出


def test_cli_entry_prompts_from_cache(tmp_path, monkeypatch, capsys):
    """CLI 入口：缓存有新版 → stderr 一行；且 allow_fetch=False 不联网。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "pypi")
    (tmp_path / "cache").mkdir(parents=True)
    (tmp_path / "cache" / "update-check.json").write_text(
        json.dumps({"feed": "pypi", "latest": "9.9.9", "checked_at": time.time()}))
    called = []
    monkeypatch.setattr(uc, "_fetch_latest", lambda f, timeout=uc.FETCH_TIMEOUT: called.append(f) or "x")
    uc.cli_notify(["update-now-ish"])  # 非豁免子命令（任意串）
    err = capsys.readouterr().err
    assert "[nexus] v9.9.9 available" in err
    assert not called  # 入口路径零同步网络


def test_server_notify_one_line(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_FEED", "off")
    lines = []
    uc.server_notify(lines.append)  # off → 零输出零异常
    assert lines == []


def test_ver_compare_matrix():
    """比较矩阵（1970 真机自检段固化）：前导数字+稳态>预发布。"""
    matrix = [
        ("1.0.1", "1.0.0a1", True), ("1.0.0", "1.0.0a1", True),
        ("1.1.0", "1.0.0", True), ("1.0.0", "1.0.0", False),
        ("", "1.0.0", False), ("2.0", "1.9.9", True), ("v3.0.0", "3.0.0", False),
    ]
    for latest, current, want in matrix:
        assert uc.is_newer(latest, current) is want, (latest, current)
