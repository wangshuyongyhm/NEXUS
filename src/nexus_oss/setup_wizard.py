#!/usr/bin/env python3
"""nexus setup — 本地 Web 配置向导 v2（Task 1577，1576 v1 升级）。

v2 变化（用户定向 0933：「这些 key 是可以自定义新增删减的」）：
- 平台列表不再硬编码——读 ~/.nexus/providers.json（providers.py 单一真源），
  表单动态渲染，重进向导即反映增删
- 页内「添加自定义平台」（id/名称/env 变量/帮助链接/探活四要素）与「删除」
  （内置平台也可删，出厂模板在代码里可一键恢复）
- 自定义平台探活：通用 HTTP（GET/POST/HEAD + {VAR} 替换 + 可配预期状态码）；
  内置平台沿用平台专用探活模板

红线不变：真实 key 绝不进仓库——.env 写 ~/.nexus/.env（仓库目录之外）；
API 响应/日志只回显字段名与结论，绝不回显值。

测试钩子：字段值 "STUB:" 前缀 → 打自身 /api/_echo（绿链路不出网）。
"""
import json
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nexus_oss import providers as pv  # noqa: E402 — Provider 注册表单一真源

ENV_PATH = Path(os.environ.get("NEXUS_ENV_FILE",
                               Path.home() / ".nexus" / ".env"))

_TEST_TIMEOUT = 8
_MAX_LIFETIME_S = 30 * 60

# ── A 修（1579-A High）：Host 白名单 + CSRF token ──────────────────────────
# CSRF：每次向导进程启动生成一次性 token，仅嵌入本服务返回的页面（同源策略
# 使跨 Origin 网页读不到它）；所有变更类 POST（增删平台/save/test/finish）
# 必须带 X-Setup-Token 头。Host 白名单：非 127.0.0.1/localhost/[::1] 拒绝
# ——堵 DNS rebinding（rebinding 请求的 Host 是攻击者域名）。
_CSRF_TOKEN = secrets.token_urlsafe(32)
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}

# 变更类端点（除它们外 GET 只读不需 token）
_MUTATION_PATHS = {"/api/test", "/api/save", "/api/providers/add",
                   "/api/providers/remove", "/api/providers/restore_builtin",
                   "/api/finish"}


def _host_ok(host_header: str) -> bool:
    """Host 头是否为本机回环（剥端口后比对；HTTP/1.1 无 Host 也拒）。"""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 字面量 [::1]:port
        host = host.split("]")[0] + "]"
    else:
        host = host.split(":")[0]
    return host in _ALLOWED_HOSTS


def _origin_ok(origin_header: str, host_header: str) -> bool:
    """Origin 头（浏览器跨源 POST 必带）若存在，必须与本机 Host 同源。"""
    if not origin_header:
        return True  # 非浏览器客户端（curl）无 Origin——token 已足够
    o = origin_header.strip().lower().rstrip("/")
    return o in ("http://" + host_header.strip().lower(),
                 "http://127.0.0.1", "http://localhost")


def _redact(text: str, field_values) -> str:
    """探活错误信息打码：出现的任何已提交字段值替换为 ***（B 修配套）。

    Task1585（1584 BYPASS 根修）：对每个值同时替换三种形态——
      1. 原值（原始字节形态）
      2. repr 转义形态 repr(v)[1:-1]：str(InvalidURL) 等异常消息对 URL 做
         Python repr 转义（控制字符 \x00 单字节 → '\\x00' 4 字符字面量），
         原值 replace 对它失配 → 转义形态半截泄露（1584 实测）
      3. str(v)：非 str 输入的字符串化形态（防御）
    repr(v) 带引号整体出现在消息中的形态由 2 的子串覆盖。
    """
    out = text
    for v in field_values:
        if v is None:
            continue
        v = str(v)
        if len(v) >= 4 and not v.startswith("STUB:"):
            out = out.replace(v, "***")
        escaped = repr(v)[1:-1]  # 去引号的转义形态（与消息内嵌形态一致）
        if escaped != v and len(escaped) >= 4:
            out = out.replace(escaped, "***")
    return out

_ENV_KEY_RE = re.compile(r"^([A-Z0-9_]+)\s*=")


# ── 内置平台探活模板（test.type=="builtin" 时按 template 名分发）────────────

def _http_json(method, url, headers=None, payload=None, timeout=_TEST_TIMEOUT):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read() or b"{}"
        try:
            return r.status, json.loads(raw)
        except json.JSONDecodeError:
            return r.status, {}


def _builtin_probe(template: str, values: list) -> tuple:
    """内置平台探活（values 与该平台 fields 一一对应）。返回 (ok, message)。"""
    try:
        if template == "zhipu":
            status, _ = _http_json(
                "POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers={"Authorization": f"Bearer {values[0]}",
                         "Content-Type": "application/json"},
                payload={"model": "glm-4-flash", "max_tokens": 1,
                         "messages": [{"role": "user", "content": "ping"}]})
            if status == 200:
                return True, "key 有效 ✓（glm-4-flash 1-token 探活）"
            return False, f"平台拒绝（HTTP {status}）——key 可能无效"
        if template == "kimi":
            status, _ = _http_json(
                "GET", "https://api.moonshot.cn/v1/models",
                headers={"Authorization": f"Bearer {values[0]}"})
            if status == 200:
                return True, "key 有效 ✓（models 列表可达）"
            return False, f"平台拒绝（HTTP {status}）——key 可能无效"
        if template == "deepseek":
            status, _ = _http_json(
                "GET", "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {values[0]}"})
            if status == 200:
                return True, "key 有效 ✓（models 列表可达）"
            return False, f"平台拒绝（HTTP {status}）——key 可能无效"
        if template == "openrouter":
            status, _ = _http_json(
                "GET", "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {values[0]}"})
            if status == 200:
                return True, "key 有效 ✓（/api/v1/key 查询成功）"
            return False, f"平台拒绝（HTTP {status}）——key 可能无效"
        if template == "telegram":
            status, body = _http_json(
                "GET", f"https://api.telegram.org/bot{values[0]}/getMe")
            if status == 200 and body.get("ok"):
                return True, f"bot 有效 ✓（@{body.get('result', {}).get('username', '?')}）"
            return False, f"Telegram 拒绝（HTTP {status}）——token 可能无效"
        if template == "feishu":
            status, body = _http_json(
                "POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                headers={"Content-Type": "application/json"},
                payload={"app_id": values[0], "app_secret": values[1]})
            if status == 200 and body.get("code") == 0:
                return True, "凭证有效 ✓（tenant_access_token 获取成功）"
            return False, f"飞书拒绝（code {body.get('code', status)}）——凭证可能无效"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"认证拒绝（HTTP {e.code}）——key 无效"
        return False, f"平台响应异常（HTTP {e.code}）"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = type(e).__name__ if not str(e) else str(e).split("\n")[0][:60]
        return False, f"连接失败（{reason}）——检查网络或稍后再试"
    except Exception as e:  # noqa: BLE001 — B 修（1579-B）：非法 URL/编码异常兜底
        reason = type(e).__name__ if not str(e) else str(e).split("\n")[0][:60]
        return False, f"请求异常（{reason}）——检查 key 中的特殊字符"
    return False, f"未知内置模板: {template}"


def _http_probe(test: dict, fields: dict) -> tuple:
    """自定义平台通用探活（{VAR} 渲染 + 预期状态码）。返回 (ok, message)。"""
    ok, spec_or_err = pv.render_probe(test, fields)
    if not ok:
        return False, spec_or_err
    headers = {}
    if spec_or_err.get("header"):
        k, _, v = spec_or_err["header"].partition(":")
        headers[k.strip()] = v.strip()
    try:
        req = urllib.request.Request(
            spec_or_err["url"], method=spec_or_err["method"],
            headers=headers, data=b"" if spec_or_err["method"] == "POST" else None)
        with urllib.request.urlopen(req, timeout=_TEST_TIMEOUT) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code  # 4xx/5xx 也是「有响应」——按 expect 比对
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raw = str(e).split("\n")[0]
        reason = _redact(raw, fields.values())[:60] if raw else type(e).__name__
        return False, f"连接失败（{reason}）——检查端点/网络"
    except Exception as e:  # noqa: BLE001 — B 修（1579-B）：InvalidURL（ValueError 子类）
        # 等非法 URL 字符场景原会冒泡致连接中断+key 进 traceback——兜底成友好红。
        # 打码先于截断：截断会切碎 key 使全值 replace 失配（'/a/a b…' 半截泄出实锤）
        raw = str(e).split("\n")[0]
        reason = _redact(raw, fields.values())[:60] if raw else type(e).__name__
        return False, f"请求非法（{reason}）——检查 key/端点中的特殊字符"
    expect = spec_or_err.get("expect", 200)
    if status == expect:
        return True, f"探活通过 ✓（HTTP {status} == 预期 {expect}）"
    return False, f"探活不符（HTTP {status} ≠ 预期 {expect}）"


def _test_provider(provider: dict, fields: dict, self_base: str) -> tuple:
    """按 provider.test 分发探活。返回 (ok, message)。消息永不回显 key 值。"""
    plat_fields = provider.get("fields", [])
    values = [fields.get(f["name"], "").strip() for f in plat_fields]
    if not all(values):
        return False, "有字段为空，先填完再测"
    # L3 钩子：全 STUB: 前缀 → 本地回环（绿链路不出网；对所有 test.type 生效）
    if all(v.startswith("STUB:") for v in values):
        try:
            status, _ = _http_json("GET", f"{self_base}/api/_echo")
            return status == 200, "STUB 绿色链路 ✓（本地回环，未出网）" if status == 200 else "STUB 端点异常"
        except Exception as e:  # noqa: BLE001
            return False, f"STUB 调用失败: {type(e).__name__}"
    test = provider.get("test", {})
    ttype = test.get("type", "none")
    if ttype == "builtin":
        return _builtin_probe(test.get("template", ""), values)
    if ttype == "http":
        return _http_probe(test, fields)
    return True, "该平台未配置探活（type=none），已填字段将在保存时写入 .env"


# ── .env 写入（字段顺序真源=当前 providers 注册表）─────────────────────────

def env_write(fields: dict) -> list:
    provs = pv.load_providers()
    all_names = pv.field_names(provs)
    existing = {}
    extra_lines = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = _ENV_KEY_RE.match(line.strip())
            if m:
                existing[m.group(1)] = line
            elif line.strip() and not line.strip().startswith("#"):
                extra_lines.append(line)
    written = []
    for name in all_names:
        val = (fields.get(name) or "").strip()
        if not val:
            continue  # 留空=不改已有
        existing[name] = f"{name}={val}"
        written.append(name)
    body = "\n".join([existing[n] for n in all_names if existing.get(n)])
    header = "# NEXUS local secrets — 由 `nexus setup` 写入；本文件在仓库之外，绝勿提交"
    parts = [header]
    if extra_lines:
        parts.append("\n".join(extra_lines))
    if body:
        parts.append(body)
    ENV_PATH.write_text("\n".join(parts) + "\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)
    return written


# ── 依赖自检 ────────────────────────────────────────────────────────────────

def _tcp_ok(host, port, timeout=0.6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def self_check() -> list:
    v = sys.version_info
    items = []
    if (v.major, v.minor) in ((3, 10), (3, 11)):
        items.append(("ok", f"Python {v.major}.{v.minor}"))
    else:
        items.append(("warn", f"Python {v.major}.{v.minor}（建议 3.10/3.11）"))
    items.append(("ok" if sys.prefix != sys.base_prefix else "warn",
                  "运行在虚拟环境" if sys.prefix != sys.base_prefix else "系统 Python（建议 venv）"))
    pg = _tcp_ok("127.0.0.1", 5432) or _tcp_ok("127.0.0.1", 6432)
    items.append(("ok" if pg else "warn",
                  "PostgreSQL 端口可达 (5432/6432)" if pg else "PostgreSQL 未监听（可稍后启动）"))
    items.append(("ok" if shutil.which("psql") else "warn",
                  "psql 客户端" if shutil.which("psql") else "psql 缺失（brew install postgresql@15）"))
    items.append(("ok" if pv.PROVIDERS_PATH.exists() else "info",
                  f"providers 注册表（{pv.PROVIDERS_PATH.name}，首次访问自动生成）"
                  if pv.PROVIDERS_PATH.exists() else "providers 注册表将在首次访问时生成"))
    return items


# ── 单页 HTML（动态渲染 + 页内增删 + 探活）──────────────────────────────────

_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS Setup</title>
<style>
:root{--bg:#0f1117;--panel:#161a23;--panel2:#1b2029;--line:#262d3d;--text:#e6e9f0;
--muted:#8b93a7;--accent:#4f8cff;--ok:#34c98e;--bad:#ff5d5d;--warn:#f5b455;--r:12px}
*{box-sizing:border-box}
body{margin:0;color:var(--text);font-size:15px;line-height:1.55;
 background:radial-gradient(1100px 340px at 50% -80px,#182135 0%,var(--bg) 60%);
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:26px 20px 90px}
.brand{display:flex;align-items:baseline;gap:12px;padding:4px 0 16px;border-bottom:1px solid var(--line);margin-bottom:20px}
.logo{font-size:21px;font-weight:800;letter-spacing:.5px}
.logo b{color:var(--accent)}
.tagline{color:var(--muted);font-size:13px}
.stepper{display:flex;align-items:center;margin:4px 0 24px}
.st{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;white-space:nowrap}
.st .dot{width:26px;height:26px;border-radius:50%;background:var(--panel2);border:1px solid var(--line);
 display:flex;align-items:center;justify-content:center;font-size:12px;transition:all .25s}
.st.active .dot{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}
.st.done .dot{background:var(--ok);border-color:var(--ok);color:#04150d}
.st.active{color:var(--text)}
.bar{flex:1;height:2px;background:var(--line);margin:0 10px;border-radius:1px;transition:background .3s}
.bar.fill{background:var(--ok)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:24px 26px;margin:14px 0;
 box-shadow:0 8px 28px rgba(0,0,0,.28)}
.hero h1{font-size:23px;margin:2px 0 6px}
.hero p{color:var(--muted);margin:0 0 18px}
.mini3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:2px 0 18px}
.mini{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:13px 15px;font-size:13.5px}
.mini .n{display:inline-flex;width:22px;height:22px;border-radius:50%;background:var(--accent);color:#fff;
 align-items:center;justify-content:center;font-size:12px;font-weight:700;margin-right:8px}
.mini b{display:block;margin-bottom:2px}
.mini span{color:var(--muted);font-size:12.5px}
.checklist{list-style:none;padding:0;margin:0 0 16px}
.checklist li{margin:6px 0;font-size:14px;display:flex;gap:8px;align-items:baseline}
.checklist .ic{width:18px;flex:none}
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)} .muted{color:var(--muted)}
button{padding:8px 16px;border-radius:8px;border:1px solid var(--line);background:var(--panel2);color:var(--text);
 cursor:pointer;font-size:13.5px;transition:all .15s}
button:hover{border-color:var(--accent)}
button:disabled{opacity:.55;cursor:default}
button.primary{background:linear-gradient(135deg,var(--accent),#3a6fd8);border-color:transparent;color:#fff;font-weight:600;
 box-shadow:0 4px 14px rgba(79,140,255,.25)}
button.primary:hover{filter:brightness(1.08)}
button.ghost{background:transparent}
button.danger{color:var(--bad);border-color:#5a2c33;background:transparent}
button.danger:hover{border-color:var(--bad)}
button.small{padding:4px 10px;font-size:12.5px}
.card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:13px 16px;margin:11px 0}
.card .row{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.card .acts{display:flex;gap:6px;align-items:center}
.card label{display:block;font-size:13px;margin:8px 0 3px}
.card label .help{font-size:12px;color:var(--accent);text-decoration:none;margin-left:6px}
.card input{width:100%;padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:#12151d;
 color:var(--text);font-size:14px;outline:none;transition:border .15s}
.card input:focus{border-color:var(--accent)}
.hint{font-size:12px;min-height:15px;margin:3px 0 0}
.hint.ok{color:var(--ok)} .hint.warn{color:var(--warn)}
.tst{font-size:13px;margin-left:10px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:3px 10px;border-radius:99px;
 border:1px solid var(--line);color:var(--muted)}
.badge::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--muted);opacity:.6}
.badge.pass{color:var(--ok);border-color:#1e5c43}.badge.pass::before{background:var(--ok)}
.badge.fail{color:var(--bad);border-color:#6b2f34}.badge.fail::before{background:var(--bad)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.grid input,.grid select{width:100%;padding:8px 11px;border:1px solid var(--line);border-radius:8px;
 background:#12151d;color:var(--text);font-size:13.5px;outline:none}
.grid input:focus{border-color:var(--accent)}
details.addbox{border:1px dashed var(--line);border-radius:10px;padding:12px 16px;margin:14px 0}
details.addbox summary{cursor:pointer;font-weight:600;font-size:14px;color:var(--accent)}
details.addbox[open] summary{margin-bottom:10px}
.foot-btns{display:flex;justify-content:space-between;align-items:center;margin-top:18px;gap:10px}
.preview{border:1px solid var(--line);border-radius:10px;background:var(--panel2);padding:6px 16px;margin:12px 0}
.preview .pv{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px dashed var(--line);font-size:13.5px}
.preview .pv:last-child{border-bottom:none}
.code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#0b0d13;border:1px solid var(--line);
 border-radius:8px;padding:9px 13px;font-size:13px;color:#9cc4ff;display:inline-block;margin:4px 0}
.sumrow{display:flex;justify-content:space-between;align-items:center;padding:9px 2px;border-bottom:1px dashed var(--line);font-size:14px}
.sumrow:last-child{border-bottom:none}
.nextbox{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-top:14px}
.nextbox h3{margin:0 0 8px;font-size:14px}
.foot{margin-top:26px;text-align:center;font-size:12.5px}
.toast{position:fixed;top:-70px;left:50%;transform:translateX(-50%);padding:10px 22px;border-radius:99px;
 background:#1e2531;border:1px solid var(--line);font-size:14px;transition:top .3s;z-index:9;box-shadow:0 8px 22px rgba(0,0,0,.4)}
.toast.show{top:20px}
.toast.ok{border-color:#1e5c43;color:var(--ok)} .toast.bad{border-color:#6b2f34;color:var(--bad)}
</style></head><body>
<div class="wrap">
<header class="brand">
 <div class="logo">◆ NE<b>X</b>US</div>
 <div class="tagline">多 Agent 协作编排调度框架 · 本地配置向导</div>
</header>

<div class="stepper">
 <div class="st" id="st1"><span class="dot">1</span>欢迎</div><div class="bar"></div>
 <div class="st" id="st2"><span class="dot">2</span>平台 Key</div><div class="bar"></div>
 <div class="st" id="st3"><span class="dot">3</span>保存</div><div class="bar"></div>
 <div class="st" id="st4"><span class="dot">4</span>完成</div>
</div>

<section class="panel hero" id="s1">
 <h1>三步完成接入</h1>
 <p>你的 key 只写入本机 ~/.nexus/.env（仓库目录之外），绝不进仓库、不上传。</p>
 <div class="mini3">
  <div class="mini"><b><span class="n">1</span>填写平台 Key</b><span>内置六平台 + 任意自定义平台</span></div>
  <div class="mini"><b><span class="n">2</span>逐项连通测试</b><span>红绿即时反馈，填错立刻知道</span></div>
  <div class="mini"><b><span class="n">3</span>写入本地 .env</b><span>权限 600，未填项保持原样</span></div>
 </div>
 <h3 style="font-size:15px;margin:14px 0 8px">环境自检</h3>
 <ul class="checklist" id="checklist"><li class="muted">检测中…</li></ul>
 <button class="primary" onclick="goStep(2)">开始配置 →</button>
</section>

<section class="panel" id="s2" style="display:none">
 <h2 style="font-size:17px;margin:0 0 4px">平台 Key</h2>
 <p class="muted" style="margin:0 0 10px;font-size:13px">可只填你在用的平台；每张卡可单独测试连通。</p>
 <div id="cards"><p class="muted">加载平台列表…</p></div>

 <details class="addbox" id="np_form">
  <summary id="addTitle">＋ 添加自定义平台</summary>
  <div class="grid">
   <input id="np_id" placeholder="平台 id（小写，如 my-llm）">
   <input id="np_label" placeholder="显示名称（如 My LLM）">
   <input id="np_env" placeholder="key 的环境变量名（如 MY_LLM_KEY）">
   <input id="np_help" placeholder="帮助链接（可选）">
   <input id="np_url" placeholder="探活 URL，{VAR} 会替换成 key 值">
   <select id="np_method"><option>GET</option><option>POST</option><option>HEAD</option></select>
   <input id="np_header" placeholder="探活 header（如 X-Api-Key: {MY_LLM_KEY}，可选）">
   <input id="np_expect" type="number" value="200" placeholder="预期状态码">
  </div>
  <p class="muted" style="font-size:12px;margin:8px 0 10px">探活可选：清空 URL = 不探活（type=none），保存时只写 .env。</p>
  <button class="primary small" id="addBtn" onclick="addPlatform(this)">添加平台</button>
  <button class="ghost small" style="display:none" id="cancelEdit" onclick="resetAddForm()">取消编辑</button>
  <span class="st" id="addSt"></span>
 </details>

 <div class="foot-btns">
  <div>
   <button class="ghost small" onclick="restoreBuiltin(this)">恢复内置平台</button>
   <span class="st" id="rbSt"></span>
  </div>
  <div>
   <button class="ghost" onclick="goStep(1)">← 上一步</button>
   <button class="primary" onclick="goStep(3)">保存并继续 →</button>
  </div>
 </div>
</section>

<section class="panel" id="s3" style="display:none">
 <h2 style="font-size:17px;margin:0 0 4px">确认保存</h2>
 <p class="muted" style="margin:0 0 8px;font-size:13px">以下新填写的 key 将写入 ~/.nexus/.env（值仅本地显示为掩码）。</p>
 <div class="preview" id="savePreview"><div class="pv muted">尚无新填写的 key——可返回上一步填写</div></div>
 <div class="foot-btns">
  <button class="ghost" onclick="goStep(2)">← 返回修改</button>
  <button class="primary" id="saveBtn" onclick="saveKeys(this)">写入 .env 并完成 →</button>
 </div>
</section>

<section class="panel" id="s4" style="display:none">
 <h2 style="font-size:17px;margin:0 0 4px">配置完成</h2>
 <div id="summary" style="margin:10px 0 4px"></div>
 <div class="nextbox">
  <h3>下一步</h3>
  <div>查看调度层可见的平台状态：</div>
  <div class="code">~/.nexus/venv/bin/nexus providers</div>
  <div class="muted" style="font-size:12.5px;margin-top:6px">Provider 语义与调度接入契约见 docs/agent-providers.md</div>
 </div>
 <div class="foot-btns">
  <button class="ghost" onclick="goStep(2)">← 补填平台</button>
  <button class="primary" id="finBtn" onclick="finish(this)">完成并关闭服务</button>
 </div>
 <span class="st" id="finSt" style="margin-left:10px"></span>
</section>

<footer class="foot muted">key 真值只落本机 ~/.nexus/.env · 平台注册表 ~/.nexus/providers.json 可增删（向导页内即可管理）</footer>
</div>
<div class="toast" id="toast"></div>

<script>
const TOKEN='__CSRF_TOKEN__';
const PATTERNS={
 ZHIPU_API_KEY:/^[A-Za-z0-9]{24,48}$/,
 KIMI_API_KEY:/^sk-[A-Za-z0-9]{16,}$/,
 DEEPSEEK_API_KEY:/^sk-[A-Za-z0-9]{16,}$/,
 OPENROUTER_API_KEY:/^sk-or-[A-Za-z0-9-]{16,}$/,
 TELEGRAM_BOT_TOKEN:/^[0-9]{8,}:[A-Za-z0-9_-]{30,}$/,
 FEISHU_APP_ID:/^cli_[a-z0-9]{8,}$/,
 FEISHU_APP_SECRET:/^[A-Za-z0-9]{18,}$/};
let PLATFORMS=[],badge={},typed={},editingId=null,confirmDel=null,finished=false;
function el(id){return document.getElementById(id)}
function setSt(e,ok,m){e.textContent=m;e.className='st '+(ok?'ok':'bad')}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function mask(v){return v.length<=8?'••••••':v.slice(0,3)+'••••••'+v.slice(-2)}
let toastTimer=null;
function toast(msg,kind){const t=el('toast');t.textContent=msg;t.className='toast show '+(kind||'');
 clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.className='toast',2400)}

function goStep(n){
 for(let i=1;i<=4;i++) el('s'+i).style.display=(i===n?'block':'none');
 document.querySelectorAll('.st').forEach(s=>s.classList.remove('active','done'));
 for(let i=1;i<n;i++) el('st'+i).classList.add('done');
 el('st'+n).classList.add('active');
 document.querySelectorAll('.bar').forEach((b,i)=>b.classList.toggle('fill',i+1<n));
 if(n===3) renderPreview();
 if(n===4) renderSummary();
 window.scrollTo({top:0,behavior:'smooth'});
}

async function check(){
 const r=await fetch('/api/check');const d=await r.json();
 el('checklist').innerHTML=d.items.map(([s,m])=>
  `<li><span class="ic">${s==='ok'?'✅':(s==='warn'?'⚠️':'ℹ️')}</span><span class="${s==='ok'?'ok':(s==='warn'?'warn':'muted')}">${esc(m)}</span></li>`).join('');
}
check();

async function loadPlatforms(){
 const r=await fetch('/api/providers');const d=await r.json();
 PLATFORMS=d.providers;renderCards();
}
function setBadge(pid){
 const b=el('bdg_'+pid); if(!b) return;
 const s=badge[pid];
 b.className='badge'+(s==='pass'?' pass':(s==='fail'?' fail':''));
 b.textContent=s==='pass'?'已通过':(s==='fail'?'未通过':'未测');
}
function renderCards(){
 let h='';
 for(const p of PLATFORMS){
  h+=`<div class="card" id="card_${esc(p.id)}"><div class="row">
   <div class="acts"><b>${esc(p.label)}</b>
    <span class="muted" style="font-size:12px">${p.builtin?'内置':'自定义'}</span>
    <span class="badge" id="bdg_${esc(p.id)}">未测</span></div>
   <div class="acts">
    <button class="ghost small" onclick="editPlatform('${esc(p.id)}')">编辑</button>
    <button class="danger small" onclick="delPlatform('${esc(p.id)}',this)">删除</button>
   </div></div>`;
  for(const f of p.fields){
   h+=`<label>${esc(f.label)} ${f.help?`<a class="help" href="${esc(f.help)}" target="_blank">去哪获取 ↗</a>`:''}</label>
    <input id="f_${esc(f.name)}" placeholder="${esc(f.placeholder||'')}" autocomplete="off"
     value="${esc(typed[f.name]||'')}" oninput="onKeyInput(this,'${esc(f.name)}')"
     onkeydown="if(event.key==='Enter'){event.preventDefault();testOne('${esc(p.id)}',this.closest('.card'))}">
    <div class="hint" id="hint_${esc(f.name)}"></div>`;
  }
  h+=`<div class="row" style="margin-top:8px"><button class="small tbtn" onclick="testOne('${esc(p.id)}',this.closest('.card'))">测试连通</button><span class="tst"></span></div></div>`;
 }
 if(!h) h='<p class="muted">平台列表为空——点下方「恢复内置平台」或添加自定义平台。</p>';
 el('cards').innerHTML=h;
 for(const p of PLATFORMS) setBadge(p.id);
}
loadPlatforms();

function fieldsOf(p){const o={};for(const f of p.fields){o[f.name]=(typed[f.name]||'').trim()}return o}
function onKeyInput(inp,name){
 typed[name]=inp.value.trim();
 const h=el('hint_'+name); if(!h) return;
 const v=typed[name],pat=PATTERNS[name];
 if(!v||!pat){h.textContent='';h.className='hint';return;}
 if(pat.test(v)){h.textContent='✓ 格式看起来正确';h.className='hint ok';}
 else{h.textContent='格式与典型形态不同（仍可测试/保存）';h.className='hint warn';}
}
async function post(path,body){
 const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Setup-Token':TOKEN},
  body:JSON.stringify(body||{})});
 let d={};try{d=await r.json()}catch(e){}
 return {status:r.status,...d};
}
async function testOne(pid,card){
 const st=card.querySelector('.tst');const btn=card.querySelector('.tbtn');
 const old=btn.textContent;btn.disabled=true;btn.textContent='测试中…';st.textContent='';st.className='tst';
 const p=PLATFORMS.find(x=>x.id===pid);if(!p){btn.disabled=false;btn.textContent=old;return;}
 const d=await post('/api/test',{platform_id:pid,fields:fieldsOf(p)});
 badge[pid]=d.ok?'pass':'fail';setBadge(pid);
 st.textContent=(d.ok?'✓ ':'✗ ')+d.message;st.className='tst '+(d.ok?'ok':'bad');
 try{st.animate([{opacity:0,transform:'translateY(-3px)'},{opacity:1,transform:'none'}],{duration:220});}catch(e){}
 btn.disabled=false;btn.textContent=old;
}
function editPlatform(pid){
 const p=PLATFORMS.find(x=>x.id===pid);if(!p)return;
 editingId=pid;
 el('np_id').value=p.id;el('np_id').disabled=true;
 el('np_label').value=p.label;
 const f=p.fields[0]||{};
 el('np_env').value=f.name||'';el('np_env').disabled=true;
 el('np_help').value=f.help||'';
 const t=p.test||{};
 if(t.type==='http'){el('np_url').value=t.url||'';el('np_method').value=t.method||'GET';
  el('np_header').value=t.header||'';el('np_expect').value=t.expect||200;}
 else el('np_url').value='';
 el('addTitle').textContent='编辑平台：'+p.label;
 el('addBtn').textContent='保存修改';
 el('cancelEdit').style.display='inline-block';
 el('np_form').open=true;
 el('np_form').scrollIntoView({behavior:'smooth',block:'center'});
}
function resetAddForm(){
 editingId=null;
 ['np_id','np_label','np_env','np_help','np_url','np_header'].forEach(i=>{el(i).value='';el(i).disabled=false;});
 el('np_expect').value='200';el('np_method').value='GET';
 el('addTitle').textContent='＋ 添加自定义平台';
 el('addBtn').textContent='添加平台';
 el('cancelEdit').style.display='none';
 el('addSt').textContent='';
}
async function addPlatform(btn){
 const id=el('np_id').value.trim(),env=el('np_env').value.trim(),url=el('np_url').value.trim();
 const body={id,label:el('np_label').value.trim()||id,
  fields:[{name:env,label:'API Key',help:el('np_help').value.trim(),placeholder:''}],
  test:url?{type:'http',method:el('np_method').value,url,header:el('np_header').value.trim(),
   expect:parseInt(el('np_expect').value||'200',10)}:{type:'none'}};
 if(editingId){
  const rm=await post('/api/providers/remove',{id:editingId});
  if(!rm.ok){setSt(el('addSt'),false,'❌ '+rm.message);return;}
 }
 const d=await post('/api/providers/add',body);
 if(d.ok){const verb=editingId?'已保存修改':'已添加平台';resetAddForm();loadPlatforms();toast(verb,'ok');
  setSt(el('addSt'),true,'✅ '+verb);}
 else setSt(el('addSt'),false,'❌ '+(d.message||'添加失败'));
}
async function delPlatform(pid,btn){
 if(confirmDel!==pid){
  confirmDel=pid;const old=btn.textContent;btn.textContent='确认删除？';
  setTimeout(()=>{if(confirmDel===pid){btn.textContent='删除';confirmDel=null;}},2600);
  return;
 }
 confirmDel=null;
 const d=await post('/api/providers/remove',{id:pid});
 if(d.ok){delete badge[pid];loadPlatforms();toast('平台已删除','ok');}
 else toast(d.message||'删除失败','bad');
}
async function restoreBuiltin(btn){
 const d=await post('/api/providers/restore_builtin',{});
 if(d.ok){setSt(el('rbSt'),true,'✅ 内置平台已补回');loadPlatforms();}
}
function renderPreview(){
 const rows=PLATFORMS.flatMap(p=>p.fields.map(f=>({p,f}))).filter(x=>(typed[x.f.name]||'').trim());
 el('savePreview').innerHTML=rows.length
  ?rows.map(x=>`<div class="pv"><span>${esc(x.f.name)} <span class="muted">（${esc(x.p.label)}）</span></span><span class="code" style="padding:2px 10px">${esc(mask(typed[x.f.name]))}</span></div>`).join('')
  :'<div class="pv muted">尚无新填写的 key——可返回上一步填写（已保存过的项不受影响）</div>';
}
async function saveKeys(btn){
 const all={};for(const p of PLATFORMS){Object.assign(all,fieldsOf(p));}
 const filled=Object.entries(all).filter(([,v])=>v);
 if(!filled.length){toast('没有新填写的 key（.env 未变更）','');goStep(4);return;}
 btn.disabled=true;const old=btn.textContent;btn.textContent='写入中…';
 const d=await post('/api/save',{fields:all});
 btn.disabled=false;btn.textContent=old;
 if(d.ok){toast('已写入 ~/.nexus/.env：'+(d.written||[]).join(', '),'ok');goStep(4);}
 else toast(d.message||'保存失败','bad');
}
function renderSummary(){
 let h='';
 for(const p of PLATFORMS){
  const miss=p.fields.filter(f=>!(typed[f.name]||'').trim());
  const b=badge[p.id];
  h+=`<div class="sumrow"><div><b>${esc(p.label)}</b> <span class="muted" style="font-size:12px">${p.builtin?'内置':'自定义'}</span></div>
   <div class="acts" style="display:flex;gap:8px">
    <span class="badge ${miss.length?'':'pass'}">${miss.length?'未配置（缺 '+miss.map(f=>esc(f.name)).join(', ')+'）':'已配置'}</span>
    ${b?`<span class="badge ${b}">${b==='pass'?'测试通过':'测试未通过'}</span>`:''}
   </div></div>`;
 }
 el('summary').innerHTML=h||'<p class="muted">无平台——可返回添加。</p>';
}
async function finish(btn){
 const d=await post('/api/finish',{});
 if(d.ok!==false&&d.ok!==true&&d.status&&d.status!==200){toast('关闭失败','bad');return;}
 finished=true;
 el('st4').classList.add('done');
 setSt(el('finSt'),true,'✅ 服务已自动停止，本页可关闭');
 btn.disabled=true;btn.textContent='已关闭';
}
const DEMO=new URLSearchParams(location.search).has('demo');
if(DEMO){typed={ZHIPU_API_KEY:'STUB-demo-zhipu-0123456789',KIMI_API_KEY:'',DEEPSEEK_API_KEY:'sk-demo-badformat',TELEGRAM_BOT_TOKEN:''};badge={zhipu:'pass',deepseek:'fail'};}
const hStep=parseInt(location.hash.slice(1),10);
if(hStep>=1&&hStep<=4) goStep(hStep);
document.addEventListener('keydown',e=>{
 if(e.key!=='Enter')return;
 if(el('s1').style.display!=='none'){e.preventDefault();goStep(2);}
});
</script></body></html>"""



# ── HTTP 服务（v2 API：providers 增删 + 动态 test）─────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "nexus-setup/0.2"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        # A 修：Host 白名单（DNS rebinding 请求的 Host 是攻击者域名 → 拒）
        if not _host_ok(self.headers.get("Host", "")):
            self._send(403, {"error": "forbidden host"})
            return
        # Task1587（#239）：统一剥 query 再路由——精确匹配 self.path 对 /?demo=1
        # 这类带 query 的 URL 全部落 404（1586 验收实锤）。query 丢弃不管
        # （页面 JS 自己读 location.search，服务端不需要）。
        path = urlsplit(self.path).path
        if path == "/":
            page = (_PAGE
                    .replace("__PLATFORMS_JSON__", json.dumps(pv.load_providers(), ensure_ascii=False))
                    .replace("__CSRF_TOKEN__", _CSRF_TOKEN))
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif path == "/api/check":
            self._send(200, {"items": self_check()})
        elif path == "/api/providers":
            self._send(200, {"providers": pv.load_providers()})
        elif path == "/api/_echo":
            self._send(200, {"stub": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        # A 修：Host 白名单 + 变更类端点 CSRF token（跨 Origin 网页拿不到
        # token——同源策略；无 token 的增删/测试触发一律 403）
        if not _host_ok(self.headers.get("Host", "")):
            self._send(403, {"error": "forbidden host"})
            return
        # Task1587（#239）：剥 query 后再做 _MUTATION_PATHS 判定与路由匹配——
        # 确保 /api/save?x=1 这类带 query 的变更请求依然全过三层闸
        # （剥 query 只为路由可达，闸判定不因 query 逃逸）。
        path = urlsplit(self.path).path
        if path in _MUTATION_PATHS:
            if not _origin_ok(self.headers.get("Origin", ""),
                              self.headers.get("Host", "")):
                self._send(403, {"error": "forbidden origin"})
                return
            if self.headers.get("X-Setup-Token") != _CSRF_TOKEN:
                self._send(403, {"error": "missing/invalid setup token"})
                return
        if path == "/api/test":
            body = self._json_body()
            provs = {p["id"]: p for p in pv.load_providers()}
            provider = provs.get(body.get("platform_id", ""))
            if not provider:
                self._send(400, {"ok": False, "message": "未知平台（可能刚被删除，刷新页表）"})
                return
            base = f"http://127.0.0.1:{self.server.server_address[1]}"
            ok, msg = _test_provider(provider, body.get("fields") or {}, base)
            self._send(200, {"ok": ok, "message": msg})
        elif path == "/api/save":
            try:
                written = env_write(self._json_body().get("fields") or {})
                self._send(200, {"ok": True, "written": written})
            except OSError as e:
                self._send(500, {"ok": False, "message": f".env 写入失败: {type(e).__name__}"})
        elif path == "/api/providers/add":
            body = self._json_body()
            ok, reason = pv.add_provider(body)
            self._send(200 if ok else 400, {"ok": ok, "message": reason or "added"})
        elif path == "/api/providers/remove":
            body = self._json_body()
            ok, reason = pv.remove_provider(body.get("id", ""))
            self._send(200 if ok else 404, {"ok": ok, "message": reason or "removed"})
        elif path == "/api/providers/restore_builtin":
            provs = pv.restore_builtin()
            self._send(200, {"ok": True, "count": len(provs)})
        elif path == "/api/finish":
            self._send(200, {"ok": True})
            _tm = threading.Timer(1.0, self.server.shutdown)
            _tm.daemon = True
            _tm.start()
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


def run(env_file: str = "") -> int:
    """起向导服务（阻塞直到完成/超时）。返回 0。"""
    global ENV_PATH
    if env_file:
        ENV_PATH = Path(env_file).expanduser()
    # 访问前确保注册表存在（首次运行即生成出厂预置，页表非空）
    pv.load_providers()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"[nexus setup] 向导已启动: {url}")
    print(f"[nexus setup] .env 目标: {ENV_PATH} | 平台注册表: {pv.PROVIDERS_PATH}")
    _life = threading.Timer(_MAX_LIFETIME_S, srv.shutdown)
    _life.daemon = True
    _life.start()
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    try:
        srv.serve_forever(poll_interval=0.2)
    finally:
        srv.server_close()
        print("[nexus setup] 服务已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else ""))
