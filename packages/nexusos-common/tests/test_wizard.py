#!/usr/bin/env python3
"""test_wizard.py — 1965 向导 CLI 单测（factsheet 探测/幂等/doctor/端口换/三选）。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nexusos_common import cli
from nexusos_common.wizard import config as cfg
from nexusos_common.wizard import doctor as doc
from nexusos_common.wizard import factsheet as fs
from nexusos_common.wizard import provision as prov
from nexusos_common.wizard import scan as scan_mod

# ── factsheet 探测（HOME 重定向可测） ───────────────────────

def test_factsheet_five_agents():
    assert {a["id"] for a in fs.AGENTS} == {"claude-code", "codex", "zcode", "kimi", "cursor"}


def test_detect_agents_tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert fs.detect_agents() == []
    (tmp_path / ".zcode").mkdir()
    (tmp_path / ".cursor" / "mcp.json").parent.mkdir(parents=True)
    (tmp_path / ".cursor" / "mcp.json").write_text("{}", encoding="utf-8")
    hits = {a["id"] for a in fs.detect_agents()}
    assert hits == {"zcode", "cursor"}


def test_snippet_all_port_rerender():
    snaps = fs.snippet_all(port=29998)
    assert len(snaps) == 5 and all("29998" in s["snippet"] for s in snaps)
    toml = [s for s in snaps if s["format"] == "toml"]
    assert len(toml) == 1 and toml[0]["agent"] == "codex"


# ── Phase1 扫描 ────────────────────────────────────────────

def test_scan_json_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "nx"))
    r = scan_mod.scan_all(pg_dsn="postgresql://127.0.0.1:59999/none")  # 无 PG 口
    codes = {c["code"] for c in r["checks"]}
    assert {"os", "python", "pg", "ports", "obsidian", "disk"} <= codes
    assert r["checks"][1]["ok"] is True  # python ≥3.11
    assert "pg" in r["summary"]["negotiables"]  # 59999 无 PG → 可协商


def test_macos_perms_default_off(monkeypatch, tmp_path):
    """陷阱2：默认不扫 TCC（只有显式 --macos-perms 才查）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    r = scan_mod.scan_all(macos_perms=False)
    assert all(c["code"] != "macos-perms" for c in r["checks"])


# ── 端口自动换 ──────────────────────────────────────────────

def test_allocate_ports_skips_used():
    new = prov.allocate_ports({"xdr": 19998}, used={19999})
    assert new["xdr"] not in (19998, 19999) and new["xdr"] > 19998


# ── Phase3 幂等 ────────────────────────────────────────────

def test_write_env_idempotent(tmp_path):
    r1 = cfg.write_env({"xdr": 19998}, "postgresql://localhost/nexus_mem", home=tmp_path)
    assert r1["created"] is True
    r2 = cfg.write_env({"xdr": 19998}, "postgresql://localhost/other", home=tmp_path)
    assert r2["created"] is False  # 不覆盖
    body = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "nexus_mem" in body and "other" not in body
    assert oct(os.stat(tmp_path / ".env").st_mode & 0o777) == "0o600"
    assert "NEXUS_MASTER_KEY=" in body and len(body.split("NEXUS_MASTER_KEY=")[1].splitlines()[0]) == 36


def test_starter_vault_never_outside_default(tmp_path):
    r = cfg.write_starter_vault(tmp_path / "vault-starter")
    assert (tmp_path / "vault-starter" / "05-System" / "NEXUS-CONSTRAINT" / "index.md").is_file()
    r2 = cfg.write_starter_vault(tmp_path / "vault-starter")
    assert r2["created"] == []  # 二次零新增


def test_agent_registration_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fake"))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    reg = cfg.write_agent_registration([{"id": "zcode", "name": "ZCode", "found_via": ["~/.zcode/"]}],
                                       home=tmp_path)
    assert (tmp_path / "agents-detected.json").is_file()
    names = {Path(p).name for p in reg["snippets"]}
    assert {"claude-code.json", "codex.toml", "kimi.json", "cursor.json", "zcode.json"} == names


# ── doctor ─────────────────────────────────────────────────

def test_doctor_green_after_init(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_VAULT_ROOT", str(tmp_path))  # 哨兵/env 双保险隔离
    cfg.write_env({"xdr": 19998}, "none", home=tmp_path)
    cfg.write_agent_registration([], home=tmp_path)
    monkeypatch.setattr(fs, "detect_agents", list)  # 本机实体不泄入测试
    r = doc.doctor(pg_dsn=None)
    statuses = {d["item"]: d["status"] for d in r["diffs"]}
    assert statuses.get("PG") == "degraded"  # xdr-only 在案=可接受绿
    assert r["all_green"] is True


def test_doctor_reports_missing_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    r = doc.doctor()
    assert any(d["status"] == "missing" and d["item"] == ".env" for d in r["diffs"])
    assert r["all_green"] is False


# ── CLI 全自动路径（--json 无交互） ─────────────────────────

def test_cli_scan_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "nx"))
    rc = cli.main(["init", "--scan", "--json", "--pg-dsn", "postgresql://127.0.0.1:59999/x"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["phase"] == "scan" and "checks" in out


def test_cli_init_c_path_full_auto(tmp_path, monkeypatch, capsys):
    """矩阵 C 路：vault C 降级 + PG C 降级，全自动无 TTY。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "nx"))
    monkeypatch.delenv("NEXUS_VAULT_ROOT", raising=False)
    rc = cli.main(["init", "--json", "--vault", "c", "--pg", "c",
                   "--pg-dsn", "postgresql://127.0.0.1:59999/x"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["ok"] is True
    assert out["choices"] == {"vault": "c", "pg": "c"}
    assert "损失清单" in out["provision"]["detail"]
    assert (tmp_path / "nx" / ".env").is_file()


def test_cli_init_b_starter_docker(tmp_path, monkeypatch, capsys):
    """矩阵 B/Docker 路：vault B starter + PG A docker 片段（不替跑 docker）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "nx"))
    rc = cli.main(["init", "--json", "--vault", "b", "--pg", "a",
                   "--pg-dsn", "postgresql://127.0.0.1:59999/x"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["vault"]["path"].endswith("vault-starter")
    idx = tmp_path / "nx" / "vault-starter" / "05-System" / "NEXUS-CONSTRAINT" / "index.md"
    assert idx.is_file()


def test_cli_init_idempotent_second_run(tmp_path, monkeypatch, capsys):
    """验收关2：二次 init 零变更（env 不覆盖；vault 零新增）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "nx"))
    for _ in range(2):
        rc = cli.main(["init", "--json", "--vault", "b", "--pg", "c",
                       "--pg-dsn", "postgresql://127.0.0.1:59999/x"])
        assert rc == 0
    env1 = (tmp_path / "nx" / ".env").read_text(encoding="utf-8")
    rc = cli.main(["init", "--json", "--vault", "b", "--pg", "c",
                   "--pg-dsn", "postgresql://127.0.0.1:59999/x"])
    env2 = (tmp_path / "nx" / ".env").read_text(encoding="utf-8")
    assert env1 == env2  # master_key 等零漂移
