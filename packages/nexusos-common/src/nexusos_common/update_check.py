"""nexusos_common.update_check — 启动时更新提示（1970，后台+24h 缓存+零遥测）。

设计铁律（任务书）：
- 主流程零阻塞：CLI 入口只读缓存（文件读 <1ms）+ 后台守护线程刷新缓存（不打印）
- 24h 缓存落 $NEXUS_HOME/cache/update-check.json（latest/checked_at/feed）
- feed 可配 NEXUS_UPDATE_FEED=github|pypi|off（默认 off——公开后文档引导开；
  GitHub 匿名限频 60/h 风险靠默认 off+缓存双保险）
- 离线/超时 3s 静默跳过（旧缓存保留，永不抛异常）
- 零上报：纯拉取版本号，不回传任何用户数据
- 版本比较自持（lockstep 语义：四包同版本线，比对代表包即代表全家）
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from nexusos_common import __version__, nexus_home

CACHE_MAX_AGE = 86400  # 24h
FETCH_TIMEOUT = 3.0
FEED_ENV = "NEXUS_UPDATE_FEED"
REPO_ENV = "NEXUS_UPDATE_REPO"
PYPI_PKG_ENV = "NEXUS_UPDATE_PYPI_PKG"
DEFAULT_REPO = "wangshuyongyhm/nexusos-xdr"
DEFAULT_PYPI_PKG = "nexusos-xdr"
# CLI 入口豁免子命令（update 本身就是检查；init 引导流不搅扰；doctor 有专节）
_EXEMPT_SUBCMDS = {"init", "doctor", "update", "setup"}


def current_version() -> str:
    """已装 nexusos-common 版（lockstep 代表）；importlib 失败回落包内 __version__。"""
    try:
        from importlib.metadata import version as _dist_version
        return _dist_version("nexusos-common")
    except Exception:  # noqa: BLE001 —— 未安装态回落包内版本
        return __version__


def _cache_path() -> Path:
    return nexus_home() / "cache" / "update-check.json"


def _read_cache() -> dict | None:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 —— 缓存缺失/损坏=无缓存语义
        return None


def _write_cache(data: dict) -> None:
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001, S110 —— 缓存写失败静默（提示机制不因缓存故障炸）
        pass


def _feed() -> str:
    return (os.environ.get(FEED_ENV, "") or "off").strip().lower()


def _fetch_latest(feed: str, timeout: float = FETCH_TIMEOUT) -> str | None:
    """拉最新版号（纯拉取零上报）。失败返 None（调用方静默）。"""
    if feed == "pypi":
        pkg = os.environ.get(PYPI_PKG_ENV, DEFAULT_PYPI_PKG)
        url = f"https://pypi.org/pypi/{pkg}/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))["info"]["version"]
    if feed == "github":
        repo = os.environ.get(REPO_ENV, DEFAULT_REPO)
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tag = json.loads(resp.read().decode("utf-8")).get("tag_name", "")
            return tag.lstrip("v") or None
    return None


def _ver_tuple(v: str) -> tuple:
    """粗粒度版本序（零依赖）：每段 (前导数字, 是否净数字段)；净数字段 >
    带预发布后缀段（PEP 440 稳态>预发布近似）；后缀号不细分（v1 够用）。"""
    out = []
    for part in (v or "").strip().lstrip("v").split("."):
        lead = ""
        for ch in part:
            if ch.isdigit():
                lead += ch
            else:
                break
        out.append((int(lead) if lead else 0, 1 if part.isdigit() else 0))
    return tuple(out) or ((0, 0),)


def is_newer(latest: str, current: str) -> bool:
    try:
        return _ver_tuple(latest) > _ver_tuple(current)
    except Exception:  # noqa: BLE001 —— 非常规版本串按"不提示"处理（fail-soft）
        return False


def get_update_status(allow_fetch: bool = False, feed: str | None = None) -> dict:
    """状态单源（CLI 提示/doctor/server 三入口共用）。

    allow_fetch=False（CLI 入口默认）：只读缓存（零网络零阻塞）+由调用方另行
    触发后台刷新；True（doctor/显式检查）：缓存过期时同步拉一次（≤3s）。
    off → 永不联网；任何失败 → 静默 error 态，旧缓存保留。
    """
    cur = current_version()
    f = feed or _feed()
    if f not in ("github", "pypi"):
        return {"feed": "off", "current": cur, "latest": None,
                "checked_at": None, "update_available": False}
    cached = _read_cache()
    now = time.time()
    fresh = bool(cached and cached.get("feed") == f
                 and now - float(cached.get("checked_at") or 0) < CACHE_MAX_AGE)
    if fresh:
        latest = cached.get("latest")
        return {"feed": f, "current": cur, "latest": latest, "checked_at": cached.get("checked_at"),
                "update_available": is_newer(latest or "", cur), "from_cache": True}
    if not allow_fetch:
        # 陈旧/无缓存：回旧值（若有）供提示，刷新交后台
        latest = (cached or {}).get("latest")
        return {"feed": f, "current": cur, "latest": latest,
                "checked_at": (cached or {}).get("checked_at"),
                "update_available": is_newer(latest or "", cur), "from_cache": bool(cached)}
    try:
        latest = _fetch_latest(f)
        if latest:
            rec = {"feed": f, "latest": latest, "checked_at": now}
            _write_cache(rec)
            return {"feed": f, "current": cur, "latest": latest, "checked_at": now,
                    "update_available": is_newer(latest, cur), "from_cache": False}
    except Exception:  # noqa: BLE001, S110 —— 离线/超时/限频统一静默（旧缓存兜）
        pass
    return {"feed": f, "current": cur, "latest": (cached or {}).get("latest"),
            "checked_at": (cached or {}).get("checked_at"),
            "update_available": is_newer((cached or {}).get("latest") or "", cur),
            "error": "fetch-failed", "from_cache": bool(cached)}


def notify_line(status: dict) -> str | None:
    """新版提示行（同版/无数据/off → None 零输出）。"""
    if status.get("update_available") and status.get("latest"):
        return (f"[nexus] v{status['latest']} available → "
                f"pipx upgrade {DEFAULT_PYPI_PKG} && nexus update")
    return None


def start_refresh_thread() -> None:
    """后台守护线程刷新缓存（不打印不 join——主流程零阻塞）。"""
    if _feed() not in ("github", "pypi"):
        return
    t = threading.Thread(target=lambda: get_update_status(allow_fetch=True), daemon=True)
    t.start()


def cli_notify(argv: list[str] | None = None) -> None:
    """CLI 入口提示（stderr 一行；--json/--no-check/init/doctor/update 豁免）。"""
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--json" in argv or "--no-check" in argv:
        return  # 陷阱2：不污染 JSON 通道；显式禁用
    sub = next((a for a in argv if not a.startswith("-")), "")
    if sub in _EXEMPT_SUBCMDS:
        return
    status = get_update_status(allow_fetch=False)  # 零网络零阻塞
    start_refresh_thread()  # 缓存刷新后台走（下次启动见效）
    line = notify_line(status)
    if line:
        print(line, file=sys.stderr)


def server_notify(log_fn) -> None:
    """mcp_server 启动日志一行（一次性；feed off/同版/无缓存 → 零输出）。"""
    try:
        status = get_update_status(allow_fetch=False)
        start_refresh_thread()
        line = notify_line(status)
        if line:
            log_fn(line)
    except Exception:  # noqa: BLE001, S110 —— 提示机制永不炸服务启动
        pass
