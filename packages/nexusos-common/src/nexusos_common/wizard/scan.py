"""wizard.scan — Phase1 环境扫描（只读，spec §1）。

分级：block（阻断）/negotiable（三选）/auto（自动换）/info（信息）。
PG 探测 psycopg2 懒加载（nexusos-common 零依赖红线——缺席=skip 项非崩溃）。
"""
from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
from pathlib import Path

from nexusos_common import nexus_home
from nexusos_common.wizard.factsheet import DEFAULT_PORTS, detect_agents


def _check(code: str, name: str, level: str, ok: bool, detail: str, extra: dict | None = None):
    return {"code": code, "name": name, "level": level, "ok": ok,
            "status": "✓" if ok else ("⚠️" if level != "block" else "✗"),
            "detail": detail, **(extra or {})}


def probe_os() -> dict:
    s = platform.system()
    supported = s == "Darwin" or s == "Linux"
    return _check("os", f"OS/架构 {s}/{platform.machine()}",
                  "block" if s not in ("Darwin", "Linux") else "info", supported,
                  "macOS✓ / Linux 支持" if supported else f"{s} 如实报未支持（v1）")


def probe_python() -> dict:
    v = sys.version_info
    ok = v >= (3, 11)
    return _check("python", f"Python {v.major}.{v.minor}.{v.micro}", "block", ok,
                  "≥3.11" if ok else "需 ≥3.11（阻断）")


def probe_pg(dsn: str | None) -> dict:
    """PG 试连+pgvector 扩展查询（可协商三选）。psycopg2 缺席=依赖未装（skip 语义）。"""
    dsn = dsn or "postgresql://localhost/postgres"
    try:
        import psycopg2  # 懒加载：零依赖红线
    except ImportError:
        return _check("pg", "PostgreSQL", "negotiable", False,
                      "psycopg2 未装（pip install nexusos-mem 或 psycopg2-binary 后复扫）",
                      {"stage": "driver-missing"})
    try:
        conn = psycopg2.connect(dsn, connect_timeout=3)
    except Exception as e:  # noqa: BLE001 —— 连接失败=三选协商项（psycopg2 各类错误统一入报告）
        return _check("pg", "PostgreSQL", "negotiable", False,
                      f"试连失败：{type(e).__name__}: {e}", {"stage": "no-conn", "dsn_shown": _mask_dsn(dsn)})
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname='vector'")
            has_vec = cur.fetchone() is not None
            cur.execute("SELECT 1 FROM pg_available_extensions WHERE name='vector'")
            avail_vec = cur.fetchone() is not None
        detail = f"可连（vector 扩展{'已装' if has_vec else '未装但可装' if avail_vec else '不可用'}）"
        return _check("pg", "PostgreSQL", "negotiable", True, detail,
                      {"stage": "ok", "has_pgvector": has_vec, "pgvector_available": avail_vec})
    finally:
        conn.close()


def _mask_dsn(dsn: str) -> str:
    if "@" in dsn and "://" in dsn:
        head, tail = dsn.split("@", 1)
        scheme = head.split("://", 1)[0]
        return f"{scheme}://***@{tail}"
    return dsn


def probe_ports() -> dict:
    """六端口逐个 bind 探测（可自动换）。"""
    rows, conflicts = {}, {}
    for name, port in DEFAULT_PORTS.items():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                rows[name] = {"port": port, "free": True}
            except OSError:
                rows[name] = {"port": port, "free": False}
                conflicts[name] = port
    return _check("ports", "六端口占用", "auto", not conflicts,
                  "全空闲" if not conflicts else f"冲突：{conflicts}（Phase2 自动换）",
                  {"ports": rows})


def probe_obsidian() -> dict:
    """进程+常见 vault 位置+用户自指（env NEXUS_VAULT_ROOT）。"""
    import os
    env_vault = os.environ.get("NEXUS_VAULT_ROOT", "").strip()
    cands = []
    if env_vault:
        cands.append(("env NEXUS_VAULT_ROOT", env_vault, Path(env_vault).is_dir()))
    home = Path(os.environ.get("HOME", str(Path.home())))
    for rel in ("Documents/Obsidian", "Obsidian", "Documents/ObsidianVault"):
        p = home / rel
        if p.is_dir() and (p / ".obsidian").is_dir():
            cands.append((f"~/{rel}", str(p), True))
    running = False
    try:
        out = subprocess.run(["pgrep", "-fl", "Obsidian"], capture_output=True, text=True, timeout=3, check=False)
        running = bool(out.stdout.strip())
    except Exception:  # noqa: BLE001, S110 —— pgrep 缺席平台降级（探测性 pass）
        pass
    ok = bool(cands)
    detail = f"候选 {len(cands)} 个（进程{'在' if running else '不在'}）" if ok else \
             "未发现（可协商三选：指向目录/starter vault/降级）"
    return _check("obsidian", "Obsidian/vault", "negotiable", ok, detail,
                  {"candidates": [{"via": v, "path": p, "valid": okk} for v, p, okk in cands],
                   "process_running": running})


def probe_disk_writable() -> dict:
    home = nexus_home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        ok, detail = True, f"{home} 可写"
    except OSError as e:
        ok, detail = False, f"{home} 不可写：{e}（Phase2 权限分支）"
    return _check("disk", "磁盘/.nexus 可写", "block", ok, detail)


def probe_macos_perms(enabled: bool) -> dict | None:
    """macOS 权限（仅 OCRX 启用时检查——spec 条款：别默认扫 TCC 惹弹窗）。"""
    if not enabled or platform.system() != "Darwin":
        return None
    import subprocess
    def _tcc(service: str) -> str:
        try:
            out = subprocess.run(["sqlite3", f"{Path.home()}/Library/Application Support/com.apple.TCC/TCC.db",
                                  f"SELECT auth_value FROM access WHERE service='{service}' LIMIT 1;"],
                                 capture_output=True, text=True, timeout=3, check=False)
            v = out.stdout.strip()
            return "granted" if v == "2" else ("denied" if v else "unknown(可能需用户授权后复扫)")
        except Exception:  # noqa: BLE001 —— TCC db 缺席=unknown 降级
            return "unknown"
    full = _tcc("kTCCServiceSystemPolicyAllFiles")
    axx = _tcc("kTCCServiceAccessibility")
    return _check("macos-perms", f"macOS 全盘访问={full}/辅助功能={axx}", "negotiable",
                  full == "granted" or axx == "granted",
                  "指引：系统设置 > 隐私与安全性 > 完全磁盘访问权限/辅助功能",
                  {"full_disk": full, "accessibility": axx})


def scan_all(pg_dsn: str | None = None, macos_perms: bool = False) -> dict:
    """Phase1 全项扫描。返回 {checks: [...], agents: [...], summary: {...}}。"""
    checks = [probe_os(), probe_python(), probe_pg(pg_dsn), probe_ports(),
              probe_obsidian(), probe_disk_writable()]
    mp = probe_macos_perms(macos_perms)
    if mp:
        checks.append(mp)
    agents = detect_agents()
    blockers = [c["code"] for c in checks if c["level"] == "block" and not c["ok"]]
    negotiables = [c["code"] for c in checks if c["level"] in ("negotiable", "auto") and not c["ok"]]
    return {
        "checks": checks,
        "agents": [{"id": a["id"], "name": a["name"], "found_via": a["found_via"]} for a in agents],
        "summary": {"blockers": blockers, "negotiables": negotiables,
                    "agents_detected": len(agents)},
    }


def render_table(result: dict) -> str:
    lines = ["环境扫描（Phase1，只读）", "", "| 检查项 | 状态 | 分级 | 说明 |", "|---|---|---|---|"]
    for c in result["checks"]:
        lines.append(f"| {c['name']} | {c['status']} | {c['level']} | {c['detail']} |")
    for a in result["agents"]:
        lines.append(f"| Agent: {a['name']} | ✓ | info | 命中 {a['found_via']} |")
    s = result["summary"]
    lines += ["", f"阻断 {len(s['blockers'])}｜可协商 {len(s['negotiables'])}｜Agent 命中 {s['agents_detected']} 家",
              json.dumps({"blockers": s["blockers"], "negotiables": s["negotiables"]}, ensure_ascii=False)]
    return "\n".join(lines)
