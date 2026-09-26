"""providers.py — 动态 Provider 注册表（Task 1577 向导 v2）。

单一真源：~/.nexus/providers.json（env NEXUS_AGENT_PROVIDERS 可指向别处）。
- 内置六平台模板出厂预置（builtin=true，可删可改可复制——删了也能「恢复内置」）
- 自定义平台四要素：名称/env 变量名/帮助链接/探活方式（generic HTTP 或 builtin 模板复用）
- 向导表单动态渲染自本表；xdr/agent-registry 侧读同一文件（NEXUS_AGENT_PROVIDERS
  语义：新平台加入后调度层可见——本模块 load_providers() 即消费接口）

格式选 JSON 而非 TOML：stdlib tomllib 只读、无写库（--no-deps 骨架无 tomli-w），
增删改需要写回——JSON 双向 stdlib 安全（negative-results 记录该取舍）。

schema（version 1）：
{
  "version": 1,
  "providers": [
    {"id": "zhipu", "label": "...", "builtin": true,
     "fields": [{"name": "ZHIPU_API_KEY", "label": "API Key",
                 "help": "https://...", "placeholder": "..."}],
     "test": {"type": "builtin", "template": "zhipu"}},
    {"id": "my-llm", "label": "My LLM", "builtin": false,
     "fields": [{"name": "MY_LLM_KEY", ...}],
     "test": {"type": "http", "method": "GET",
              "url": "https://api.example.com/v1/me",
              "header": "Authorization: Bearer {MY_LLM_KEY}",
              "expect": 200}}
  ]
}
"""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

PROVIDERS_PATH = Path(os.environ.get(
    "NEXUS_AGENT_PROVIDERS",
    str(Path.home() / ".nexus" / "providers.json")))

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,40}$")

# ── 内置模板（出厂预置；test.template 名即此处 key——探活逻辑在向导侧）──────

BUILTIN_PROVIDERS = [
    {
        "id": "zhipu", "label": "智谱 BigModel（GLM）", "builtin": True,
        "fields": [
            {"name": "ZHIPU_API_KEY", "label": "API Key",
             "help": "https://open.bigmodel.cn/usercenter/apikeys",
             "placeholder": "32 位左右，控制台「API Keys」页创建"},
        ],
        "test": {"type": "builtin", "template": "zhipu"},
    },
    {
        "id": "kimi", "label": "Kimi（Moonshot）", "builtin": True,
        "fields": [
            {"name": "KIMI_API_KEY", "label": "API Key",
             "help": "https://platform.moonshot.cn/console/api-keys",
             "placeholder": "sk- 开头"},
        ],
        "test": {"type": "builtin", "template": "kimi"},
    },
    {
        "id": "deepseek", "label": "DeepSeek", "builtin": True,
        "fields": [
            {"name": "DEEPSEEK_API_KEY", "label": "API Key",
             "help": "https://platform.deepseek.com/api_keys",
             "placeholder": "sk- 开头"},
        ],
        "test": {"type": "builtin", "template": "deepseek"},
    },
    {
        "id": "openrouter", "label": "OpenRouter（可选聚合）", "builtin": True,
        "fields": [
            {"name": "OPENROUTER_API_KEY", "label": "API Key",
             "help": "https://openrouter.ai/keys",
             "placeholder": "sk-or- 开头"},
        ],
        "test": {"type": "builtin", "template": "openrouter"},
    },
    {
        "id": "telegram", "label": "Telegram Bot", "builtin": True,
        "fields": [
            {"name": "TELEGRAM_BOT_TOKEN", "label": "Bot Token",
             "help": "https://t.me/BotFather（/newbot 后获得）",
             "placeholder": "数字:字母串，如 123456:AA..."},
        ],
        "test": {"type": "builtin", "template": "telegram"},
    },
    {
        "id": "feishu", "label": "飞书开放平台", "builtin": True,
        "fields": [
            {"name": "FEISHU_APP_ID", "label": "App ID",
             "help": "https://open.feishu.cn/app（企业自建应用「凭证与基础信息」）",
             "placeholder": "cli_ 开头"},
            {"name": "FEISHU_APP_SECRET", "label": "App Secret",
             "help": "https://open.feishu.cn/app（同页「App Secret」）",
             "placeholder": "同页凭证区"},
        ],
        "test": {"type": "builtin", "template": "feishu"},
    },
]


def _validate(p: dict, existing_ids: set) -> tuple:
    """校验单个 provider 结构。返回 (ok, reason)。"""
    if not isinstance(p, dict):
        return False, "provider 必须是对象"
    pid = p.get("id", "")
    if not _ID_RE.match(pid or ""):
        return False, f"id 非法（小写字母开头，含 a-z0-9_-，≤31 字符）: {pid!r}"
    if pid in existing_ids:
        return False, f"id 已存在: {pid}"
    if not p.get("label"):
        return False, "label 不能为空"
    fields = p.get("fields")
    if not isinstance(fields, list) or not fields:
        return False, "至少一个字段"
    for f in fields:
        if not _ENV_RE.match(f.get("name", "")):
            return False, f"字段名非法（大写字母开头 A-Z0-9_）: {f.get('name')!r}"
        if not f.get("label"):
            return False, "字段 label 不能为空"
    test = p.get("test", {})
    ttype = test.get("type")
    if ttype == "builtin":
        if test.get("template") not in {b["id"] for b in BUILTIN_PROVIDERS}:
            return False, f"未知 builtin 模板: {test.get('template')!r}"
    elif ttype == "http":
        url = test.get("url", "")
        if not url.startswith(("http://", "https://")):
            return False, "http 探活 url 必须以 http(s):// 开头"
        if test.get("method", "GET").upper() not in ("GET", "POST", "HEAD"):
            return False, "method 仅支持 GET/POST/HEAD"
        expect = test.get("expect", 200)
        if not isinstance(expect, int) or not (100 <= expect < 600):
            return False, "expect 必须是 100-599 的状态码"
        header = test.get("header", "")
        if header and not re.match(r"^[A-Za-z-]+:\s*.+$", header):
            return False, "header 形如 'Authorization: Bearer {VAR}'"
    elif ttype == "none":
        pass
    else:
        return False, "test.type 必须是 builtin|http|none"
    return True, ""


def load_providers(path=None) -> list:
    """读注册表；文件缺失/损坏时写出厂预置并返回之（自愈式首次初始化）。"""
    p = Path(path) if path else PROVIDERS_PATH
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            provs = data.get("providers")
            if isinstance(provs, list):
                return provs
        except (json.JSONDecodeError, OSError):
            pass  # 损坏 → 重建出厂（用户自定义丢失但可重加；保向导永不空白）
    save_providers(BUILTIN_PROVIDERS, p)
    return [dict(b) for b in BUILTIN_PROVIDERS]


def save_providers(providers: list, path=None) -> None:
    """C 修（1579-C）：原子写——同目录 tmp 文件 + os.replace（rename 原子性），
    进程崩溃/磁盘满不再留半写损坏文件。"""
    import tempfile as _tf
    p = Path(path) if path else PROVIDERS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": 1, "providers": providers},
                         ensure_ascii=False, indent=2) + "\n"
    fd, tmp = _tf.mkstemp(dir=str(p.parent), prefix=".providers-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)  # POSIX rename：读者要么见旧文件要么见新完整文件
        try:
            os.chmod(p, 0o644)  # 无密钥（模板/链接），无需 600
        except OSError:
            pass
    except OSError:
        try:
            os.unlink(tmp)  # 失败清理残渣（处女原则：不留 .tmp 尾巴）
        except OSError:
            pass
        raise


# C 修：读-改-写全程持锁（进程内 threading 锁保向导多请求并发；跨进程用
# 同目录 .providers.lock flock——cli/向导同时操作注册表的场景）。
import fcntl as _fcntl  # noqa: E402 — POSIX only（macOS/Linux，与产品定位一致）
import threading as _threading  # noqa: E402

_WRITE_LOCK = _threading.RLock()


@contextmanager
def _locked(path):
    """写锁：进程内 RLock + 跨进程 flock（.providers.lock 同目录侧车文件）。"""
    lock_path = (Path(path) if path else PROVIDERS_PATH).parent / ".providers.lock"
    with _WRITE_LOCK:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "w")
        try:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            yield
        finally:
            try:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            finally:
                fh.close()


def add_provider(provider: dict, path=None) -> tuple:
    """追加自定义平台（校验后落盘）。C 修：读-改-写全程持锁。返回 (ok, reason)。"""
    with _locked(path):
        provs = load_providers(path)
        ok, reason = _validate(provider, {p.get("id") for p in provs})
        if not ok:
            return False, reason
        provider = dict(provider)
        provider.setdefault("builtin", False)
        provs.append(provider)
        save_providers(provs, path)
        return True, ""


def remove_provider(pid: str, path=None) -> tuple:
    """删除平台（内置也可删——出厂模板仍在代码里可恢复）。C 修：持锁。返回 (ok, reason)。"""
    with _locked(path):
        provs = load_providers(path)
        rest = [p for p in provs if p.get("id") != pid]
        if len(rest) == len(provs):
            return False, f"id 不存在: {pid}"
        save_providers(rest, path)
        return True, ""


def restore_builtin(path=None) -> list:
    """把内置模板补回注册表（不覆盖同名自定义项）。C 修：持锁。返回合并后列表。"""
    with _locked(path):
        provs = load_providers(path)
        have = {p.get("id") for p in provs}
        for b in BUILTIN_PROVIDERS:
            if b["id"] not in have:
                provs.append(dict(b))
        save_providers(provs, path)
        return provs


def field_names(providers: list) -> list:
    """全部字段的 env 变量名（.env 写入顺序真源）。"""
    return [f["name"] for p in providers for f in p.get("fields", [])]


def configured_providers(env_file=None) -> list:
    """NEXUS_AGENT_PROVIDERS 的 runtime 侧读取接口（Task 1577 目标 3 占位）。

    语义：xdr / agent-registry 等调度层消费者读同一注册表（本函数），即可
    感知向导新增的平台——新平台加入并配好 key 后对调度层可见。调度逻辑
    本体的接入不在本单（接口占位 + docs/agent-providers.md 契约说明）。

    返回 [{"id", "label", "builtin", "ready", "missing"}]：
    ready=True 表示该平台全部字段都已在 .env 配置（dispatch-ready）。
    """
    import re as _re
    env_path = Path(env_file) if env_file else Path(
        os.environ.get("NEXUS_ENV_FILE", str(Path.home() / ".nexus" / ".env")))
    env_vals = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = _re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
            if m:
                env_vals[m.group(1)] = m.group(2).strip()
    out = []
    for p in load_providers():
        missing = [f["name"] for f in p.get("fields", [])
                   if not env_vals.get(f["name"])]
        out.append({"id": p["id"], "label": p.get("label", p["id"]),
                    "builtin": bool(p.get("builtin")),
                    "ready": not missing, "missing": missing})
    return out


_BRACE_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute(template: str, fields: dict) -> tuple:
    """{VAR} 替换（1577 快验抓的 bug：string.Template 是 $VAR 语法，与本模块
    约定的 {VAR} 不符替换不生效——改自研正则替换）。

    规则：只替换 fields 里非空的变量；非字段的花括号原样保留；
    引用了字段但值空 → (False, 报错)（带字面 {VAR} 出请求=探活必假）。
    """
    def repl(m):
        name = m.group(1)
        if fields.get(name):
            return fields[name]
        return m.group(0)
    out = _BRACE_RE.sub(repl, template)
    for m in _BRACE_RE.finditer(out):
        if m.group(1) in fields:
            return False, f"探活引用了未填写的字段: {m.group(1)}"
    return True, out


def render_probe(test: dict, fields: dict) -> tuple:
    """把自定义 http 探活描述渲染成实际请求参数（{VAR} 替换）。返回 (ok, spec|reason)。

    仅用于 test.type == "http"；builtin 由向导侧模板函数处理。
    """
    ok_url, url_or_err = _substitute(test.get("url", ""), fields)
    if not ok_url:
        return False, url_or_err
    header = test.get("header", "")
    if header:
        ok_h, header_or_err = _substitute(header, fields)
        if not ok_h:
            return False, header_or_err
        header = header_or_err
    return True, {"url": url_or_err, "header": header,
                  "method": test.get("method", "GET").upper(),
                  "expect": test.get("expect", 200)}
