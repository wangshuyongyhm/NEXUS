#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_engine.py — NEXUS Gate 声明式门禁引擎(调度核心)。

只做 4 件事,永远不因新场景/新检查而修改:
  1. 加载场景 YAML
  2. 校验 required_context 齐全
  3. 按检查 type 分发到 _checks/ 插件 + 汇总 pass/fail + 分级
  4. 进场景前自动解析注入 vault_root(Task696 自 format,裸调治本)

检查逻辑独立成 etc/gates/_checks/*.py 插件(启动时自动发现)。

Task630 首包化: 正源自 nexusos_xdr/gate_engine.py 迁入(旧位留 re-export shim)。
插件发现改用包绝对路径 nexusos_gate.etc.gates._checks.*(不再依赖 sys.path hack)。
"""
import hashlib
import hmac
import importlib
import importlib.metadata
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# === Task 2611230853 件一：通过记录签名 ===
# 密钥同用户可读：这防的是「文字里恰好带 scenario=state_transition passed=True」造成的误认，
# 不是安全边界——同用户进程本来就能读到这把密钥。真边界在文件权限之外。
_GATE_SIG_FILE = Path.home() / ".nexus" / "xdr" / "gate.sig"



# === Task 2611230853 件六：提交说明点名文件的核对 ===
_NAMED_FILE_SUFFIXES = (".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".txt")


def _extract_named_files(commit_msg: str) -> list:
    """从提交说明里挑「像文件」的词：含路径分隔符的，或以已知后缀结尾的。去重保序。"""
    out, seen = [], set()
    for tok in re.split(r"[\s，。；、,;:：()（）\[\]「」『』\"'`]+", commit_msg or ""):
        tok = tok.strip().strip(".")
        if not tok:
            continue
        if "/" in tok or tok.endswith(_NAMED_FILE_SUFFIXES):
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


def _staged_matches(name: str, staged: list) -> bool:
    """按路径后缀匹配：说明里写短名（report.md）也能对到 task/NN/output/report.md。"""
    n = str(name).lstrip("./")
    for s in staged or []:
        sp = str(s).lstrip("./")
        if sp == n or sp.endswith("/" + n) or sp.endswith(n):
            return True
    return False


def _eval_commit_named_files(context: dict):
    """返回 (passed, detail, severity_override)。一个都没点名 → 通过（不管）。"""
    names = _extract_named_files(str((context or {}).get("commit_msg") or ""))
    if not names:
        return True, "说明里没点名文件（不管）", None
    staged = (context or {}).get("staged_files") or []
    missing = [n for n in names if not _staged_matches(n, staged)]
    if not missing:
        return True, f"说明点名的 {len(names)} 个文件都在暂存清单里", None
    if len(missing) == len(names):
        return False, "说明点名的文件都不在提交里: " + ", ".join(missing[:6]), None
    return True, "部分点名文件不在提交里(WARN): " + ", ".join(missing[:6]), "WARN"

def _gate_sig_key() -> bytes:
    """读/生成签名密钥（32 字节随机 → hex，权限 0600）。拿不到就返回空串，调用方不加签名。"""
    try:
        if _GATE_SIG_FILE.exists():
            raw = _GATE_SIG_FILE.read_bytes().strip()
            if len(raw) >= 16:
                return raw
        _GATE_SIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = os.urandom(32).hex().encode()
        _GATE_SIG_FILE.write_bytes(key)
        os.chmod(_GATE_SIG_FILE, 0o600)
        return key
    except Exception:
        return b""


def gate_sign(scenario: str, agent: str, ts: str) -> str:
    """对 `场景|实例|时间戳` 做 HMAC-SHA256，取前 16 个十六进制字符。"""
    key = _gate_sig_key()
    if not key:
        return ""
    return hmac.new(key, f"{scenario}|{agent}|{ts}".encode("utf-8"),
                    hashlib.sha256).hexdigest()[:16]


# === Task 2611230853 件五：每项检查的执行记录 ===
_GATE_EXEC_LOG = Path.home() / ".nexus" / "xdr" / "gate-exec.jsonl"
_GATE_EXEC_MAX_BYTES = 20 * 1024 * 1024


def _append_exec_log(scenario: str, agent: str, task_id: str, results: list) -> None:
    """每跑一项检查追加一行（通过也留痕，回答「是每次都过还是从来没跑」）。
    超过 20MB → 旧内容改名 .1 再新建（只留一代）。观察件：写不进去不影响门禁。"""
    try:
        if _GATE_EXEC_LOG.exists() and _GATE_EXEC_LOG.stat().st_size > _GATE_EXEC_MAX_BYTES:
            os.replace(_GATE_EXEC_LOG, Path(str(_GATE_EXEC_LOG) + ".1"))
        _GATE_EXEC_LOG.parent.mkdir(parents=True, exist_ok=True)
        # 2611230858：统一用世界时（总线自己的事件用 utc，同一条流里别混两种时区）
        # 原：ts = datetime.now().astimezone().isoformat(timespec="seconds")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with _GATE_EXEC_LOG.open("a", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps({
                    "ts": ts, "scenario": scenario, "agent": agent, "task_id": task_id,
                    "check": r.get("id"), "status": r.get("status"),
                    "severity": r.get("severity"),
                }, ensure_ascii=False) + "\n")
    except Exception:
        pass

import nexusos_common as _nxc

try:
    import yaml
except ImportError:
    sys.exit("pyyaml 未安装,gate_engine 无法工作")

ENGINE_DIR = Path(__file__).resolve().parent
# Task679 拍板 A: env 可覆盖场景目录——OSS 包内 etc/gates 只含通用插件池
# （NEXUS 自用场景不随包），用户经 NEXUS_GATES_DIR 指向自己的场景目录
# （examples/gates 即可用）。本机不设 env 时行为不变（包内路径）。
GATES_DIR = Path(os.environ.get("NEXUS_GATES_DIR") or (ENGINE_DIR / "etc" / "gates"))
# Task679 拍板 A: 插件池恒在包内（通用插件随包）——env 只覆盖场景目录；
# 外置场景引用的检查类型仍从包内 _checks 解析。
CHECKS_DIR = ENGINE_DIR / "etc" / "gates" / "_checks"

# Task1704 件二（池#286）：gate WARN 落盘观测的聚合计时缓存——同
# (scenario, warn 集) 窗口内只发 1 条 gate_warn 事件（进程内单源）。
_GATE_WARN_WINDOW_SEC = float(os.environ.get("NEXUS_GATE_WARN_WINDOW", "600"))
_WARN_EMIT_CACHE: dict = {}

# CLI 未提供身份时的兜底标记。它**不是**真 Agent（不在 AGENT_REGISTRY），
# 仅用于“调用方未声明身份”这个状态的可观测占位（见 _upgrade_agent_from_context）。
CLI_FALLBACK_AGENT = "cli"


def _plugin_warn_agent() -> str:
    """插件告警事件的归因名（Task1561 / 1547-F6）。

    原 hardcoded 'nexusos-gate' 未注册 agents 表 → 9334 行归因断层。
    统一走 NEXUS_AGENT env 链（hook/dispatchd 侧同款：env > nexus 兜底，
    兜底名是注册名，B12/归因统计不再失明）。
    """
    return os.environ.get("NEXUS_AGENT") or "nexus"


# 2611192325：插件加载诊断（显性化）——原实现只打一行 stderr（launchd 链下被
# 2>/dev/null 吞掉）+ 写 PG，monitor 侧看不到「哪个插件没跑、影响哪个检查项」。
# 这里把每次跳过的结构化原因记在模块级列表里，供 I8 等消费方显性告警。
PLUGIN_LOAD_DIAG: list = []


def _py_version_note(exc: Exception) -> str:
    """识别「Python 版本不兼容」类失败（PEP 604 的 `X | None` 在 <3.10 抛 TypeError）。"""
    msg = str(exc)
    if isinstance(exc, TypeError) and "unsupported operand type(s) for |" in msg:
        return f"需 Python >=3.10（PEP 604 注解语法）；本解释器 {sys.version.split()[0]}"
    if isinstance(exc, SyntaxError):
        return f"语法不兼容本解释器 {sys.version.split()[0]}：{getattr(exc, 'msg', exc)}"
    return ""


def _affected_gate_items(plugin_stem: str) -> str:
    """该插件 type 被哪些 gate 场景/检查项引用（说清「影响哪个检查项」）。"""
    hits = []
    try:
        for y in sorted(GATES_DIR.glob("*.yaml")):
            try:
                cfg = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            # 场景 YAML 里 type 嵌在 check 里（`- id: G8 / check: {type: complexity_aware}`），
            # 也有少量写在 items 顶层的写法——两处都认（2611192325 实测：只查顶层会误报"死插件"）。
            def _itype(item):
                c = item.get("check")
                return (c.get("type") if isinstance(c, dict) else None) or item.get("type")
            ids = [str(it.get("id")) for it in (cfg.get("items") or []) if _itype(it) == plugin_stem]
            if ids:
                hits.append(f"{y.stem}({','.join(ids)})")
    except Exception:
        pass
    return "、".join(hits) if hits else "未被任何 gate 场景引用（死插件）"


def _log_gate_plugin_warn(plugin_name: str, reason: str):
    """插件加载告警写 PG agent_activity（让 monitor 能发现死插件）。fail-open。

    NEXUS_GATE_PLUGIN_WARN_PG=0 可关（2611192325：I8 每小时会 import 一次引擎做探针，
    若也写 PG 就是 ~96 行/天 重复噪音——探针只要读 PLUGIN_LOAD_DIAG，不需要重复记账）。
    """
    if os.environ.get("NEXUS_GATE_PLUGIN_WARN_PG", "1") == "0":
        return
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="nexus_mem")
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_activity (agent_id, action, target_type, detail)
            VALUES (%s, 'gate_plugin_warn', 'gate_plugin', %s)
        """, (_plugin_warn_agent(), json.dumps({"plugin": plugin_name, "reason": reason}, ensure_ascii=False),))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass  # fail-open：PG 写失败不影响 gate 运行


def _load_check_plugins() -> dict:
    """启动时扫描 _checks/,自动加载所有检查插件。
    文件名 = 检查类型名(如 field_check.py → type: field_check)。
    每个插件必须导出 check(params, context, agent) -> (bool, str) 函数。
    """
    plugins = {}
    if not CHECKS_DIR.exists():
        return plugins
    for f in sorted(CHECKS_DIR.glob("*.py")):
        # Task1561 (1547-F6 告警风暴根因): test_* / *_test 是测试文件非插件——
        # 原当插件候选扫描→每次 import 告警 4-5 条（PG 实证 ~220/天 × 9334 行）。
        # 与 "_" 前缀同款豁免约定（C5 的 test 判定同款形态）。
        if f.name.startswith("_") or f.name.startswith("test_") or f.name.endswith("_test.py"):
            continue
        try:
            # 包绝对路径 import(Task630 迁包后不再依赖 sys.path hack):
            # nexusos_gate.etc.gates._checks.field_check
            mod_name = f"nexusos_gate.etc.gates._checks.{f.stem}"
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "check") and callable(mod.check):
                plugins[f.stem] = mod.check
            else:
                # 插件未导出 check 函数,跳过(记 stderr 不崩) + 写 PG 告警(让 monitor 发现)
                print(f"[gate_engine] 插件 {f.name} 未导出 check 函数,跳过", file=sys.stderr)
                _log_gate_plugin_warn(f.name, "未导出 check 函数")
        except Exception as e:
            # 2611192325：版本不兼容显性化——统一 WARN 前缀 + 结构化 diag + 影响面。
            # 注意：显性化 ≠ 硬跑；不兼容插件仍跳过（硬跑会让整个 gate 场景崩）。
            reason = _py_version_note(e) or f"{type(e).__name__}: {str(e)[:120]}"
            affected = _affected_gate_items(f.stem)
            PLUGIN_LOAD_DIAG.append({
                "plugin": f.name,
                "reason": reason,
                "affected": affected,
                "python": sys.version.split()[0],
            })
            print(f"[gate_engine] ⚠️ 插件 {f.name} 被跳过：{reason}；影响检查项：{affected}",
                  file=sys.stderr)
            _log_gate_plugin_warn(f.name, f"加载失败（{reason}）；影响检查项：{affected}")
    return plugins


def _load_entry_point_checks() -> dict:
    """nexusos.gate.checks 插件协议（1959 单3，design §5）：entry_points 组注入。

    - 稳定序：sorted(name)（任务书陷阱1——防 check 集合随安装顺序漂移）
    - 单条失败跳过不炸引擎（与目录扫描同款 fail-open + PG 告警）
    - 加载物须导出可调用 check(params, context, agent)；模块路径或 "mod:attr" 均可
    """
    plugins = {}
    try:
        eps = importlib.metadata.entry_points(group="nexusos.gate.checks")
    except Exception:
        return plugins
    for ep in sorted(eps, key=lambda e: e.name):
        try:
            loaded = ep.load()
            fn = loaded if callable(loaded) else getattr(loaded, "check", None)
            if callable(fn):
                plugins[ep.name] = fn
            else:
                print(f"[gate_engine] entry_point {ep.name} 未导出 check，跳过", file=sys.stderr)
                _log_gate_plugin_warn(f"entry_point:{ep.name}", "未导出 check 函数")
        except Exception as e:
            print(f"[gate_engine] entry_point {ep.name} 加载失败: {e}，跳过", file=sys.stderr)
            _log_gate_plugin_warn(f"entry_point:{ep.name}", f"加载失败: {e}")
    return plugins


def _load_user_checks_d() -> dict:
    """$NEXUS_HOME/gate/checks.d/*.yaml 用户声明式启用（1959 单3，design §5）。

    每文件结构：{scenario: <场景名>, items: [<check item>...]}——items 追加进
    对应场景（不改内置 items）。文件名 sorted 稳定序；解析失败单文件跳过
    （fail-open，stderr 记录）。NEXUS_HOME 解析单源 nexusos-common。
    """
    out: dict = {}
    d = _nxc.subpath("gate", "checks.d")
    try:
        if not d.is_dir():
            return out
        for f in sorted(d.glob("*.yaml")):
            try:
                cfg = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception as e:
                print(f"[gate_engine] checks.d/{f.name} 解析失败: {e}，跳过", file=sys.stderr)
                continue
            scenario = cfg.get("scenario", "")
            items = cfg.get("items", [])
            if scenario and isinstance(items, list) and items:
                out.setdefault(scenario, []).extend(items)
    except Exception:
        pass
    return out


# 启动时加载一次：entry_points 协议（外部注入+包内五私人 check）∪ 包内目录扫描
# （内置权威——同键时目录扫描覆盖 entry_points，外部新名正常注入）。
CHECK_PLUGINS = {**_load_entry_point_checks(), **_load_check_plugins()}
# 用户 checks.d 场景追加项（$NEXUS_HOME/gate/checks.d/*.yaml）——按需懒读后缓存。
_USER_CHECKS_D_CACHE: dict = {}

# 已下线场景（用户裁定 2026-11-24）。传入这些场景名时给明确的
# 「已下线」说明，而不是「YAML 不存在」——调用方一眼看出是退役不是路径坏了。
# 单一真源：下线/恢复只改这里。
RETIRED_SCENARIOS = {
    "loop_start": "LOOP 启动门禁已于 2026-11-24 下线：使用频率极低、内容是字段长度检查。定义文件已移出，可从版本历史恢复。",
    "loop_complete": "LOOP 退出门禁已于 2026-11-24 下线：同 loop_start。定义文件已移出，可从版本历史恢复。",
    "deploy-sync": "部署后文档同步门禁已于 2026-11-24 下线：长期零运行。定义与专属检查器已移出，可从版本历史恢复。",
}


def _load_scenario(scenario: str) -> dict:
    """加载场景 YAML。返回配置 dict。

    1959 单3：加载后追加用户 checks.d 声明式 items（$NEXUS_HOME/gate/
    checks.d/*.yaml 的 {scenario, items}）——不改内置 items，只增不改。
    """
    yaml_path = GATES_DIR / f"{scenario}.yaml"
    if not yaml_path.exists():
        if scenario in RETIRED_SCENARIOS:
            raise FileNotFoundError(RETIRED_SCENARIOS[scenario])
        raise FileNotFoundError(f"场景 YAML 不存在: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not _USER_CHECKS_D_CACHE:
        _USER_CHECKS_D_CACHE.update(_load_user_checks_d() or {"": []})
    extra_items = _USER_CHECKS_D_CACHE.get(scenario) or []
    if extra_items:
        cfg = dict(cfg or {})
        cfg["items"] = list((cfg or {}).get("items", [])) + list(extra_items)
    return cfg


def _validate_context(required: list, context: dict) -> list:
    """校验 required_context 是否齐全。返回缺失字段名列表。

    Task538 修复7: required 检查"key 存在"而非"值非空"——pre-commit hook 故意
    传 commit_msg=''（-m 模式 COMMIT_EDITMSG 未写入），P-g4 的空串视为缺失会
    拦截所有 commit。空字符串/0/False 都算"已提供"（只是空值）。
    None 视为缺失（显式传 None = 没提供）。
    """
    missing = []
    for item in required:
        name = item.get("name", "") if isinstance(item, dict) else str(item)
        is_required = item.get("required", True) if isinstance(item, dict) else True
        if is_required:
            if name not in context or context.get(name) is None:
                missing.append(name)
    return missing


def _resolve_template(value: Any, context: dict) -> Any:
    """递归解析 context 占位符({var})。支持 str/list/dict。

    衔接性修复(2026-07-29): except 补 ValueError。
    原只接 KeyError/IndexError,但 str.format 遇到非法字段名(如 shell 的
    ${VAR:-default} 被 format 当字段名 PROJECT_ROOT:-. 解析)会抛 ValueError,
    导致整个 check 崩溃。补 ValueError 让它和 KeyError 一样静默返回原串。
    """
    if isinstance(value, str):
        try:
            return value.format(**context)
        except (KeyError, IndexError, ValueError):
            return value
    elif isinstance(value, list):
        return [_resolve_template(v, context) for v in value]
    elif isinstance(value, dict):
        return {k: _resolve_template(v, context) for k, v in value.items()}
    return value


def _ensure_vault_root(cfg: dict, context: dict):
    """Task696 引擎自 format:vault_root 缺省时自动解析注入(治裸调 bad substitution)。

    与 nexusos_xdr._vault_env.resolve_gate_vault_root 同语义(1957 起锚点解析
    单源=nexusos-common,两处仅保留各自的缺 vault 策略):
    context 显式值 > env NEXUS_VAULT_ROOT > 包位置推导(common 哨兵)。
    场景不含 {vault_root} 模板时不强制——OSS 通用场景无 vault 也能跑。

    Returns:
        None: 注入成功,或场景不需要 vault_root
        str: 解析失败的人话错误(调用方 fail-fast 返回,绝不带字面量进 check
             ——_resolve_template 对缺 key 静默留原串,cwd/路径会变非法)
    """
    vr = str(context.get("vault_root") or os.environ.get("NEXUS_VAULT_ROOT") or "")
    if not vr:
        # 1957 锚点单源：哨兵推导收敛 nexusos-common（原 parents[3] 内联推导删除）
        auto_dir = _nxc.auto_scripts_dir(ENGINE_DIR)
        if auto_dir is not None:
            vr = str(auto_dir.parents[1])
    if not vr or "{" in vr or not Path(vr).is_dir():
        if "{vault_root}" not in repr(cfg):
            return None  # 场景不用 {vault_root}:不阻塞(OSS 通用场景)
        return (
            f"vault_root 不可用（解析值 {vr!r} 非存在目录）。gate YAML 已全量 "
            f"{{vault_root}} 模板化（T678），缺该 key 会静默落字面量致 cwd/路径"
            f"非法（bad substitution）——显式拒绝。设 NEXUS_VAULT_ROOT 或在 "
            f"context 传 vault_root"
        )
    context.setdefault("vault_root", vr)
    return None


# 检查项会拿这些键去拼文件路径（池 #613）。入口统一绝对化后下发：
# D1 因插件内部自行解析相对路径能找到文件，D4/D6/D8 却直接拿字面量拼——
# gate 进程 cwd ≠ 任务目录时 D4 硬红、D6/D8 静默跳过（假 pass）。
PATH_CONTEXT_KEYS = ("task_dir", "task_path", "task_path_report")


def _path_candidates(raw: str, vault_root: str) -> list:
    """相对路径的候选解析顺序：进程 cwd → vault_root（都记进诊断，供 rc=1 展示）。"""
    candidates = [os.path.abspath(raw)]
    if vault_root and not os.path.isabs(raw):
        vault_candidate = os.path.abspath(os.path.join(vault_root, raw))
        if vault_candidate not in candidates:
            candidates.append(vault_candidate)
    return candidates


def _normalize_path_context(context: dict) -> dict:
    """入口处把路径类 context 键统一绝对化后回写，返回诊断记录。

    幂等：绝对路径进来只被规范形（abspath(abspath(x)) == abspath(x)）。
    相对路径取「进程 cwd → vault_root」第一个存在的候选；都不存在时保留
    cwd 解析结果（确定性），把所有尝试过的路径记进诊断供失败明细展示。
    """
    diagnostics = {}
    vault_root = str(context.get("vault_root") or os.environ.get("NEXUS_VAULT_ROOT") or "")
    for key in PATH_CONTEXT_KEYS:
        raw = context.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        if os.path.isabs(raw):
            attempts = [os.path.abspath(raw)]
            resolved = attempts[0]
        else:
            attempts = _path_candidates(raw, vault_root)
            resolved = next((c for c in attempts if os.path.exists(c)), attempts[0])
        context[key] = resolved
        diagnostics[key] = {
            "input": raw,
            "resolved": resolved,
            "exists": os.path.exists(resolved),
            "attempted": attempts,
        }
    return diagnostics


def _path_hint_text(diagnostics: dict) -> str:
    """把路径诊断拼成一行，供失败明细/CLI stderr 展示。"""
    parts = []
    for key, info in diagnostics.items():
        state = "存在" if info["exists"] else "不存在"
        parts.append(f"{key}={info['resolved']}（{state}；尝试过: {' / '.join(info['attempted'])}）")
    return "；".join(parts)


def _attach_path_diagnostics(result: dict, diagnostics: dict) -> None:
    """给失败项补「路径诊断」尾巴（rc=1 排障最小信息面：check 名 + 文件 + 尝试路径）。"""
    if not diagnostics:
        return
    has_missing_path = any(not info.get("exists") for info in diagnostics.values())
    hint = _path_hint_text(diagnostics)
    for item in result.get("failures", []):
        if item.get("status") != "fail":
            continue
        detail = str(item.get("detail", ""))
        if has_missing_path or "rc=1" in detail or "不存在" in detail:
            item["detail"] = f"{detail}｜路径诊断: {hint}"


# Task538 修复5: on_pass 钩子注册表（从 mcp_server 下沉到 engine）
# gate_engine.check() passed 后自动触发——CLI/其他 caller 也受益
_ON_PASS_HOOKS: dict = {}  # {scenario: callback(scenario, context, result)->None}


def register_on_pass(scenario: str, callback) -> None:
    """注册 on_pass 钩子（模块加载时调，Task538 修复5）。"""
    _ON_PASS_HOOKS[scenario] = callback


def _match_exemptions(cfg: dict, context: dict) -> list:
    """池 #969-B（2611192126）：YAML 层豁免匹配。

    done.yaml 等 scenario YAML 顶层 ``exemptions:`` 段声明式定义（MEM#116515
    口径——任务书层声明豁免无效，必须 YAML 层）。规则形如::

        exemptions:
          - id: shadow-tasks
            match: {task_id_glob: "xdr-*-shadow-*"}   # 或 caller_in: [...]
            skip_items: [G1, G3, G4, G7, G12]
            mark: "exempt=shadow"

    返回命中的规则列表（skip 决策在 item 循环内按 skip_items 精确匹配）。
    """
    import fnmatch

    rules = cfg.get("exemptions") or []
    if not isinstance(rules, list):
        return []
    out = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match") or {}
        tid = str(context.get("task_id", "") or "")
        hit = False
        pat = match.get("task_id_glob")
        if pat and tid:
            hit = fnmatch.fnmatch(tid, str(pat))
        if not hit and match.get("caller_in"):
            caller = str(context.get("caller")
                         or context.get("agent") or "")
            hit = caller in match["caller_in"]
        if hit:
            out.append(rule)
    return out


def check(scenario: str, context: dict, agent: str = "") -> dict:
    """过场景门禁。返回 {passed, failures, hard_fails, warns}。

    Args:
        scenario: 场景名(done/init/dispatch/persist/code)
        context: Agent 传入的上下文(含 required_context 声明的字段)
        agent: 调用方 agent 名
    """
    context = context or {}
    # 1. 加载场景
    try:
        cfg = _load_scenario(scenario)
    except FileNotFoundError as e:
        return {"passed": False, "failures": [{"detail": str(e)}],
                "hard_fails": [{"detail": str(e)}], "warns": []}

    # 2. Task696 自 format:vault_root 自动解析注入(调用方契约下沉到引擎,
    #    裸调 from nexusos_xdr import gate_check 不再喂 vault_root 也能跑)
    vr_err = _ensure_vault_root(cfg, context)
    if vr_err:
        vr_item = {"id": "VR", "name": "vault_root 自解析", "status": "fail",
                   "severity": "REJECT", "detail": vr_err}
        return {"passed": False, "failures": [vr_item],
                "hard_fails": [vr_item], "warns": []}

    # 2.5 池 #613: 路径类 context 键入口统一绝对化（全部检查项收到的都是绝对路径，
    #     不在各 check 里各自打补丁）；诊断记录随结果下发供 rc 明细引用。
    path_diagnostics = _normalize_path_context(context)

    # 3. 校验 required_context
    missing = _validate_context(cfg.get("required_context", []), context)
    if missing:
        msg = f"缺 context 字段: {missing}"
        return {"passed": False, "failures": [{"detail": msg}],
                "hard_fails": [{"detail": msg}], "warns": []}

    # 4. 逐项检查
    results = []
    # 池 #969-B（2611192126）：YAML 层豁免——命中规则的 skip_items 项
    # status=exempt（不出 failures，可见于结果 exempted 列表；豁免≠放水，
    # 消费方（done 回调 handler）据 exempted 标记 task_state + 事件流日报）
    active_exemptions = _match_exemptions(cfg, context)
    exempted_marks = []
    for item in cfg.get("items", []):
        item_id = item.get("id", "?")
        item_name = item.get("name", item_id)
        severity = item.get("severity", "WARN")
        is_auto = item.get("auto", True)

        _ex_rule = next(
            (r for r in active_exemptions
             if item_id in (r.get("skip_items") or [])), None)
        if _ex_rule is not None:
            _ex_mark = str(_ex_rule.get("mark", _ex_rule.get("id", "exempt")))
            results.append({
                "id": item_id, "name": item_name, "status": "exempt",
                "severity": severity,
                "detail": f"豁免({_ex_rule.get('id', '?')}): {_ex_mark}",
            })
            exempted_marks.append(
                {"rule": _ex_rule.get("id"), "item": item_id,
                 "mark": _ex_mark})
            continue

        if not is_auto:
            # manual 项:只列 reminder
            results.append({
                "id": item_id, "name": item_name, "status": "manual",
                "severity": severity, "detail": item.get("reminder", "需人工确认")
            })
            continue

        check_cfg = item.get("check", {})
        check_type = check_cfg.get("type", "")
        # 解析占位符
        # Task 2611230860：检查项级别的参数（P21 的 max_files 这类）合并进 check_cfg，
        # 插件签名不用变（params 里就能看到），也不用把这些值抄进 check 子树。
        _item_params = {k: v for k, v in item.items()
                        if k not in ("id", "name", "auto", "severity", "check", "reminder")}
        if _item_params:
            check_cfg = {**_item_params, **check_cfg}
        check_cfg = _resolve_template(check_cfg, context)

        # Task 2611230853 件六：提交说明点名的文件必须在提交里（引擎内置类型，非插件）
        if check_type == "commit_named_files":
            _cok, _cdetail, _csev = _eval_commit_named_files(context)
            results.append({
                "id": item_id, "name": item_name,
                "status": "pass" if _cok else "fail",
                "severity": _csev or severity, "detail": _cdetail,
            })
            continue

        check_fn = CHECK_PLUGINS.get(check_type)
        if check_fn is None:
            results.append({
                "id": item_id, "name": item_name, "status": "fail",
                "severity": "REJECT",  # 未知检查类型 = 硬拦(防配置错)
                "detail": f"未知检查类型: {check_type}(插件 {_checks_dir_rel()}/{check_type}.py 未加载)"
            })
            continue

        try:
            ret = check_fn(check_cfg, context, agent)
            # T670 协议: 插件可返回三元组 (passed, detail, severity_override)——
            # 跨目录重定向等"降 WARN 不 REJECT"场景（line_count G4）。二元组向后兼容。
            if isinstance(ret, tuple) and len(ret) == 3:
                passed, detail, _sev_override = ret
                if not passed and _sev_override in ("WARN", "REJECT"):
                    severity = _sev_override
            else:
                passed, detail = ret
        except Exception as e:
            passed, detail = False, f"检查插件异常: {type(e).__name__}: {str(e)[:100]}"

        results.append({
            "id": item_id, "name": item_name,
            "status": "pass" if passed else "fail",
            "severity": severity, "detail": detail
        })

    # 5. 汇总
    hard_fails = [r for r in results if r["status"] == "fail" and r["severity"] == "REJECT"]
    warns = [r for r in results if r["status"] == "fail" and r["severity"] == "WARN"]
    manual = [r for r in results if r["status"] == "manual"]
    result = {
        "passed": len(hard_fails) == 0,
        "failures": results,
        "hard_fails": hard_fails,
        "warns": warns,
        "manual": manual,
    }
    # 池 #969-B：豁免明细随结果下发（handler 侧标 task_state + 事件流日报）
    if exempted_marks:
        result["exempted"] = exempted_marks
    # 池 #613: rc=1 时输出「哪个 check + 找不到哪个文件 + 尝试过的路径」
    if path_diagnostics:
        result["path_diagnostics"] = path_diagnostics
        _attach_path_diagnostics(result, path_diagnostics)
    # Task1879-B（池#352 用户裁定）: persist 场景 WARN 产生即入池 + pass 自动销账。
    # 先只 persist 域（任务书禁止过度泛化到其他场景）。fail-open：台账失败不影响 gate 结果。
    if scenario == "persist":
        try:
            from nexusos_gate import persist_pool_ledger as _ppl
            _ledger = _ppl.sync(context, result, agent=agent or context.get("agent", ""))
            if _ledger.get("registered") or _ledger.get("closed"):
                result["pool_ledger"] = _ledger
        except Exception as _ple:
            print(f"[gate_engine] WARNING: persist 池台账同步失败（不阻断 gate 结果）: "
                  f"{type(_ple).__name__}: {_ple}", file=sys.stderr)
    # Task538 修复5: on_pass 钩子在 engine 层触发（CLI/其他 caller 也受益）
    if result["passed"]:
        _hook = _ON_PASS_HOOKS.get(scenario)
        if _hook:
            import logging
            try:
                _hook(scenario, context, result)
            except Exception as _he:
                logging.getLogger("nexusos_xdr.gate_engine").warning(
                    f"[on_pass] {scenario} 钩子失败（不阻断 gate 结果）: {_he}")

    # Task609 搭车②: 内置无条件事件登记（治 import 直调无痕迹断层，用户已同意）。
    # 局部 import 防环（依赖方向 session_state 不 import 本模块——已核实）。
    # detail 格式与 mcp_server.gate_check 工具的历史登记完全一致（M8 按格式解析）；
    # mcp_server 侧重复块已删（防双写）。fail-open：登记失败绝不影响 gate 结果。
    try:
        from nexusos_xdr import session_state as _ss
        # Task2611191111 第四档：shim CLI（nexusos_xdr/gate_engine.py）不经过正源
        # __main__，只调 check()——所以这里也必须补一次，否则 shim 路径的事件
        # 仍旧落在 "cli" 上。空身份则原样返回，后续 source/caller/unknown 兜底链不变。
        _gate_agent = _upgrade_agent_from_context(agent, context) \
            or context.get("agent") or context.get("source") \
            or context.get("caller") or "unknown"
        # T657 修1: 同任务同结果只发一次事件——治 648 实证的重扫放大
        # （patrol 预检 + callback bg-gate + agent 重试回调三源都会跑 done gate，
        # 每次无条件发事件 → 同秒爆发 38 条、唯一任务仅 17-18）。
        # key 含 passed+reject 集：fail→pass 变化是新 key 自然重发（恢复信号不丢）。
        # 非 done 场景/无 task_id 照发（dispatch/persist 等本就低频）。
        _emit_evt = True
        _tid657 = context.get("task_id") or ""
        if _tid657 and scenario == "done":
            try:
                from nexusos_xdr import task_state as _ts657
                _sig657 = "gate_event:%s:%s:%s" % (
                    scenario, result.get("passed"),
                    ",".join(sorted(str(r.get("id", "?")) for r in result.get("hard_fails", []))))
                _emit_evt = _ts657.once_flag(_tid657, _sig657)
            except Exception:
                _emit_evt = True  # 判重失败→保守发（宁可重复不可丢信号）
        # Task 2611230853 件五：每项检查留执行记录（通过也留痕）
        _append_exec_log(scenario, _gate_agent, str((context or {}).get("task_id") or ""), results)
        if _emit_evt:
            # Task 2611230853 件一：state_transition 的通过记录带签名。
            # 时间戳经 extra 注入 append_event（其 event.update(extra) 在设置 ts 之后执行），
            # 所以事件里的 ts 就是这里签的那个 —— 守卫能用事件自身的 agent/ts 复算同一 HMAC。
            _sig_detail = ""
            _sig_extra = None
            if scenario == "state_transition":
                try:
                    # 2611230858：世界时；这个值同时用于签名与 extra={"ts": …}，
                    # 所以「事件 ts == 签名 ts」的性质不变（守卫用事件 ts 复算）。
                    # 原：_sig_ts = datetime.now().astimezone().isoformat(timespec="seconds")
                    _sig_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    _sig_val = gate_sign(scenario, _gate_agent, _sig_ts)
                    if _sig_val:
                        _sig_detail = f" sig={_sig_val}"
                        _sig_extra = {"ts": _sig_ts}
                except Exception:
                    _sig_detail = ""
            _tid_note = (f" task_id={context.get('task_id')}"
                         if (context or {}).get("task_id") else "")
            _ss.append_event(
                agent=_gate_agent,
                event_type="gate_check",
                detail=(f"scenario={scenario} passed={result.get('passed')} "
                        f"reject={[r.get('id', '?') for r in result.get('hard_fails', [])]} "
                        f"warn={[r.get('id', '?') for r in result.get('warns', [])]}"
                        f"{_tid_note}{_sig_detail}"),
                target=f"gate:{scenario}",
                extra=_sig_extra,
            )
        # Task1704 件二（池#286）：WARN 命中独立落 events——原 WARN 只回调用方
        # 不落盘，code 场景 3 周 262 次运行 WARN 零留存，「误报率」永远算不出。
        # 噪音控制：同 (scenario, warn 集) 短窗聚合计 1 条（模块级 TTL 缓存，
        # 进程内单源；窗口 env NEXUS_GATE_WARN_WINDOW 默认 600s），别刷爆 events。
        _warn_ids = sorted(str(r.get("id", "?")) for r in result.get("warns", []))
        if _warn_ids:
            _warn_key = f"{scenario}:{','.join(_warn_ids)}"
            _now_ts = time.time()
            _last = _WARN_EMIT_CACHE.get(_warn_key, 0.0)
            if _now_ts - _last >= _GATE_WARN_WINDOW_SEC:
                _WARN_EMIT_CACHE[_warn_key] = _now_ts
                _ss.append_event(
                    agent=_gate_agent,
                    event_type="gate_warn",
                    detail=f"scenario={scenario} warn={_warn_ids} "
                           f"hits={len(_warn_ids)} agent={_gate_agent}",
                    target=f"gate-warn:{scenario}",
                )
    except Exception as _e:
        # 1636 活③(1634 遗留): logging 无 handler 配置时 warning 被吞——补 stderr
        # 直打, "gate 事件未落流"大声可见(fail-open 语义不变: 检查主流程继续)
        import sys as _sys
        print(f"[gate_engine] WARNING: gate 事件未落流(GATE_GRACE 将看不到本次) "
              f"scenario={scenario} agent={agent}: {type(_e).__name__}: {_e}",
              file=_sys.stderr)
        import logging
        logging.getLogger("nexusos_xdr.gate_engine").warning(
            "[Task609] gate 事件写入失败 scenario=%s agent=%s: %s", scenario, agent, _e)
    return result


def _checks_dir_rel() -> str:
    """调试用:返回 _checks 相对路径。"""
    return str(CHECKS_DIR.relative_to(ENGINE_DIR))


def _resolve_cli_agent(argv: list) -> tuple:
    """CLI 落流身份解析：返回 (agent, 去掉 --agent 后的 argv)。

    MEM#95841 正修方向落地（Task2611172047）——CLI 直跑 gate 时若身份兜底
    "cli"，而 cli 不在 AGENT_REGISTRY（session_state.py:147-172 身份校验），
    append_event 必抛 ValueError → gate_check 事件不落流 → state_transition_guard
    的 60s 事件窗看不到 passed=True → dispatch 恒被拦（2010 实操整条弯路）。

    优先级（任务书 §4 裁定，与 nexus-persist-commit.sh / hook 同款口径）：
        NEXUS_AGENT env  >  --agent <name>  >  兜底 "cli"
    env 优先是为了与既有 hook/commit 链保持"同一个身份源"；--agent 只作
    显式覆盖（两者冲突时 stderr 提示，便于排障）。

    用法兼容：``gate_engine.py <scenario> '<json>' [--agent <name>]`` 与
    ``--agent=<name>`` 两种写法都认，其余位置参数原样保留。
    """
    flag_agent = ""
    kept = []
    skip_next = False
    for idx, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--agent":
            flag_agent = argv[idx + 1] if idx + 1 < len(argv) else ""
            skip_next = True
            continue
        if arg.startswith("--agent="):
            flag_agent = arg.split("=", 1)[1]
            continue
        kept.append(arg)

    # env 只在**显式设置**时优先——不能拿默认值 "cli" 冒充"env 已设"，否则
    # `--agent zcode` 在未设 env 的机器上会被默认值吃掉（B6 首轮实测踩到）。
    env_agent = (os.environ.get("NEXUS_AGENT", "") or "").strip()
    if env_agent:
        if flag_agent and flag_agent != env_agent:
            print(f"[gate] NEXUS_AGENT={env_agent} 优先于 --agent {flag_agent}"
                  "（B6：显式 env > flag > cli）", file=sys.stderr)
        return env_agent, kept
    return (flag_agent.strip() or CLI_FALLBACK_AGENT), kept


def _upgrade_agent_from_context(agent: str, context: dict) -> str:
    """身份链第四档：调用方没声明身份时，用 context.agent 补位（Task2611191111）。

    完整四档优先级（前面的赢）：
        显式 NEXUS_AGENT env  >  --agent 旗标  >  context.agent（本函数）  >  兜底 "cli"

    为什么需要这一档：CLI 直跑 gate（尤其走 shim ``nexusos_xdr/gate_engine.py``）
    时，调用模板只写 ``'{"agent":"zcode",...}'`` 而不会带 env/flag——于是身份
    落回 "cli"，而 "cli" 不在 AGENT_REGISTRY，append_event 抛 ValueError，
    gate_check 事件不落流 → state_transition_guard 看不到本次 → dispatch 被拦
    （MEM#95841 / #116823）。init/dispatch 场景的 context 本来就必带 agent，
    所以它是天然的第四档来源，不需要调用方额外记一个 flag。

    为什么只在“兜底档”生效：MEM#116823 首版的坑就是让新来源吃掉了更高优先档。
    因此这里只处理**入参为空或恰好等于兜底标记 "cli"** 的情形；一旦调用方显式
    声明了身份（env/flag），原样返回，绝不覆盖。

    校验与 append_event 同源：用 ``nexusos_xdr.session_state.validate_agent``
    （即 append_event 抛 ValueError 前调用的同一函数），不复制名单成第二真源。
    nexusos_xdr 不可达时（纯 gate 包独立部署）原样返回——那种部署本就写不了
    事件，升级与否无差别。
    """
    current = (agent or "").strip()
    if current and current != CLI_FALLBACK_AGENT:
        return current          # 更高优先档已生效，不动
    candidate = (context or {}).get("agent")
    if not isinstance(candidate, str) or not candidate.strip():
        return current      # 无候选：原样返回（空就是空，交给上层兜底链）
    candidate = candidate.strip()
    if candidate == CLI_FALLBACK_AGENT:
        return current
    try:
        from nexusos_xdr import session_state as _ss_validate
    except Exception:
        return current      # 独立包部署：无从校验，保持原态
    try:
        ok, _reason = _ss_validate.validate_agent(candidate)
    except Exception:
        return current
    return candidate if ok else current


if __name__ == "__main__":
    # CLI 调试入口:python3 gate_engine.py done '{"task_path":"...","files":[],...}'
    import json
    # B6/MEM#95841: --agent 旗标 + NEXUS_AGENT env（env > flag > cli，见 _resolve_cli_agent）
    _cli_agent, _cli_argv = _resolve_cli_agent(sys.argv[1:])
    if not _cli_argv:
        print("用法: gate_engine.py <scenario> [context_json] [--agent <name>]")
        sys.exit(2)
    scenario = _cli_argv[0]
    context = json.loads(_cli_argv[1]) if len(_cli_argv) > 1 else {}
    # Task2611191111 第四档：context 解析完才能补位（_resolve_cli_agent 跑在解析之前，
    # 那时拿不到 context）。仅当身份仍是兜底 "cli" 时才升级，env/flag 更高优先档不受影响。
    _cli_agent = _upgrade_agent_from_context(_cli_agent, context)
    # T678b 修1: CLI 不经 registry——vault_root 预注入复用 678 防线
    # （context > env NEXUS_VAULT_ROOT > 包位置推导；解析失败沿用其人话报错）
    try:
        from nexusos_xdr._vault_env import resolve_gate_vault_root
        _vr_ok, _vr = resolve_gate_vault_root(context)
        if not _vr_ok:
            print(json.dumps({"passed": False, "error": _vr}, ensure_ascii=False, indent=2))
            sys.exit(2)
    except ImportError:
        pass  # nexusos_xdr 不可达（纯 gate 包独立部署）——无注入场景照旧
    result = check(scenario, context, agent=_cli_agent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        # 池 #613: rc=1 的人读明细（哪个 check + 文件 + 尝试过的路径），JSON 仍保留机器可读
        print(f"[gate] {scenario} 未通过——失败项:", file=sys.stderr)
        for item in result.get("failures", []):
            if item.get("status") == "fail":
                print(f"  - {item.get('id')} {item.get('name')}: {item.get('detail')}", file=sys.stderr)
        for key, info in (result.get("path_diagnostics") or {}).items():
            state = "存在" if info.get("exists") else "不存在"
            print(
                f"  [路径] {key}: 输入={info.get('input')!r} → 解析={info.get('resolved')}（{state}）"
                f" 尝试过: {' / '.join(info.get('attempted') or [])}",
                file=sys.stderr,
            )
        sys.exit(1)
    sys.exit(0)
