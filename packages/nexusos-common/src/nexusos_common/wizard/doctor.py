"""wizard.doctor — 幂等复检（spec §5：对账不重写，只报差异）。

1963 合并点：本模块为 doctor 唯一实现（1963 未落骨架时）；若 1963 落
nexus update/doctor 版本轴，schema_version 对账在此对接（单一真相源）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from nexusos_common import __version__, nexus_home
from nexusos_common.wizard import scan as scan_mod
from nexusos_common.wizard.config import env_file_path
from nexusos_common.wizard.factsheet import DEFAULT_PORTS, detect_agents


def _diff_env(home: Path) -> list[dict]:
    """对账 .env：键齐全+端口与默认/声明一致+master_key 在位。不重写。"""
    f = env_file_path(home)
    if not f.is_file():
        return [{"item": ".env", "status": "missing", "detail": "未初始化（先 nexus init）"}]
    diffs = []
    text = f.read_text(encoding="utf-8")
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()
    need = ["NEXUS_PG_DSN", "NEXUS_MASTER_KEY"] + [f"NEXUS_{n.upper()}_PORT" for n in DEFAULT_PORTS]
    for k in need:
        if k not in kv:
            diffs.append({"item": f".env:{k}", "status": "missing", "detail": "键缺失（不重写——报告项）"})
    if kv.get("NEXUS_MASTER_KEY") and len(kv["NEXUS_MASTER_KEY"]) < 32:
        diffs.append({"item": ".env:NEXUS_MASTER_KEY", "status": "warn",
                      "detail": "key 长度异常（<32 hex）"})
    mode = oct(os.stat(f).st_mode & 0o777)
    if mode != "0o600":
        diffs.append({"item": ".env 权限", "status": "warn", "detail": f"当前 {mode}，建议 600"})
    return diffs


def _diff_pg(dsn_env: str) -> list[dict]:
    """DB 对账：专属库存在+extension 就绪+连接+schema 版本+角色（spec §5 全项）。"""
    if not dsn_env or dsn_env == "none":
        return [{"item": "PG", "status": "degraded", "detail": "xdr-only 降级在案（损失清单见 init 报告）"}]
    try:
        import psycopg2
    except ImportError:
        return [{"item": "PG", "status": "warn", "detail": "psycopg2 未装——DB 对账不可执行"}]
    dbname = dsn_env.rstrip("/").rsplit("/", 1)[-1] or "postgres"
    try:
        conn = psycopg2.connect(dsn_env, connect_timeout=3)
    except Exception as e:  # noqa: BLE001 —— 各类连接失败统一入对账报告
        return [{"item": "PG 连接", "status": "fail", "detail": f"{type(e).__name__}: {e}"}]
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname='vector'")
            if cur.fetchone() is None:
                return [{"item": "pgvector", "status": "fail",
                         "detail": "vector 扩展未装（CREATE EXTENSION vector;）"}]
            cur.execute("SELECT value FROM nexus_meta WHERE key='schema_version'")
            row = cur.fetchone()
            if row is None:
                return [{"item": "schema", "status": "warn",
                         "detail": "nexus_meta 不存在（旧库或未走置备——nexus init 的 B 通道补建）"}]
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname='nexus_app'")
            role_ok = cur.fetchone() is not None
    finally:
        conn.close()
    out = [{"item": "PG", "status": "ok",
            "detail": f"库 {dbname}：vector✓ schema_version={row[0]} 角色 nexus_app={'✓' if role_ok else '缺（warn）'}"}]
    if not role_ok:
        out.append({"item": "最小权限角色", "status": "warn", "detail": "nexus_app 缺（重跑 init B 通道补建）"})
    return out


def doctor(pg_dsn: str | None = None, macos_perms: bool = False) -> dict:
    """幂等复检全项。返回 {diffs, scan, agents, all_green}。"""
    home = nexus_home()
    env = env_file_path(home)
    dsn = pg_dsn
    if not dsn and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("NEXUS_PG_DSN="):
                dsn = line.split("=", 1)[1].strip()
    diffs = _diff_env(home)
    pg_diffs = _diff_pg(dsn or "none") if (dsn or "none") != "none" or not env.is_file() else \
        [{"item": "PG", "status": "degraded", "detail": "未配置（xdr-only 或未 init）"}]
    diffs += pg_diffs
    scan = scan_mod.scan_all(pg_dsn=dsn or None, macos_perms=macos_perms)
    reg = home / "agents-detected.json"
    if reg.is_file():
        try:
            registered = {a["id"] for a in json.loads(reg.read_text(encoding="utf-8")).get("agents", [])}
        except Exception:  # noqa: BLE001 —— 注册文件损坏=warn 语义不炸复检
            registered = set()
    else:
        registered = set()
    current = {a["id"] for a in detect_agents()}
    if registered != current:
        diffs.append({"item": "Agent 注册一致性", "status": "warn",
                      "detail": f"注册 {sorted(registered)} vs 当前探测 {sorted(current)}（重跑 init 刷新注册）"})
    blockers_now = [c["code"] for c in scan["checks"] if c["level"] == "block" and not c["ok"]]
    if blockers_now:
        diffs.append({"item": "阻断项", "status": "fail", "detail": f"环境阻断：{blockers_now}"})
    diffs.append({"item": "nexusos-common 版本", "status": "ok", "detail": __version__})
    # 1970 更新源对账节（current/latest/feed 固定显示；同步拉一次≤3s，off 零联网）
    from nexusos_common import update_check as _uc
    us = _uc.get_update_status(allow_fetch=True)
    if us["feed"] == "off":
        diffs.append({"item": "更新源", "status": "ok",
                      "detail": f"current={us['current']}｜feed=off（NEXUS_UPDATE_FEED=github|pypi 开启提示）"})
    elif us.get("error"):
        diffs.append({"item": "更新源", "status": "warn",
                      "detail": f"current={us['current']}｜feed={us['feed']}｜拉取失败（离线/限频，旧缓存保留）"})
    elif us.get("update_available"):
        diffs.append({"item": "更新源", "status": "warn",
                      "detail": f"current={us['current']} < latest={us['latest']}（feed={us['feed']}）→ "
                                f"pipx upgrade nexusos-xdr && nexus update"})
    else:
        diffs.append({"item": "更新源", "status": "ok",
                      "detail": f"current={us['current']}｜latest={us.get('latest') or '未知'}（feed={us['feed']}）最新"})
    all_green = all(d["status"] in ("ok", "degraded") for d in diffs) and not blockers_now
    return {"diffs": diffs, "scan": scan, "agents": sorted(current), "all_green": all_green}


def render(doctor_result: dict) -> str:
    r = doctor_result
    lines = ["doctor 幂等复检（对账不重写）", "", "| 项 | 状态 | 说明 |", "|---|---|---|"]
    for d in r["diffs"]:
        mark = {"ok": "✓", "warn": "⚠️", "fail": "✗", "missing": "✗", "degraded": "—"}.get(d["status"], "?")
        lines.append(f"| {d['item']} | {mark} {d['status']} | {d['detail']} |")
    verdict = "全绿" if r["all_green"] else "有差异（见上，未自动改动任何文件）"
    lines += ["", f"结论：{verdict}｜Agent 探测 {len(r['agents'])} 家"]
    return "\n".join(lines)
