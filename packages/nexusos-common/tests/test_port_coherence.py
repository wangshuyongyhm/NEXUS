#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_port_coherence.py — 1981 端口自洽三处单测（env 读/snippets 注入/health 回显）。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_mcp_server_port_env_priority():
    """(a) NEXUS_XDR_PORT env > 19998 默认；--port 显式最高。"""
    import importlib
    mod_path = Path(__file__).resolve().parents[2] / "nexusos-xdr" / "src"
    sys.path.insert(0, str(mod_path))
    os.environ["NEXUS_XDR_PORT"] = "20086"
    import nexusos_xdr.mcp_server as ms
    importlib.reload(ms)
    assert ms.RUNTIME_PORT == 20086, ms.RUNTIME_PORT
    del os.environ["NEXUS_XDR_PORT"]
    importlib.reload(ms)
    assert ms.RUNTIME_PORT == 19998


def test_snippets_inject_allocated_port(tmp_path, monkeypatch):
    """(b) 向导 snippets 用实际分配口（禁写死 19998）。"""
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    from nexusos_common.wizard import config as cfg
    reg = cfg.write_agent_registration([], home=tmp_path, port=20086)
    body = (tmp_path / "mcp-snippets" / "codex.toml").read_text(encoding="utf-8")
    assert "20086" in body and "19998" not in body
    for f in tmp_path.joinpath("mcp-snippets").iterdir():
        assert "20086" in f.read_text(encoding="utf-8"), f.name


def test_health_echoes_runtime_port():
    """(c) /health 的 port 字段来自 RUNTIME_PORT（回显真实监听口）。"""
    import importlib
    mod_path = Path(__file__).resolve().parents[2] / "nexusos-xdr" / "src"
    sys.path.insert(0, str(mod_path))
    os.environ["NEXUS_XDR_PORT"] = "20100"
    import nexusos_xdr.mcp_server as ms
    importlib.reload(ms)
    import inspect
    src = inspect.getsource(ms)
    assert '"port": RUNTIME_PORT' in src
    assert '"port": 19998' not in src
    del os.environ["NEXUS_XDR_PORT"]
