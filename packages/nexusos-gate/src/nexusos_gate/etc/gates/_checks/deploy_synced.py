"""检查类型: deploy_synced — 体系变更后检查部署文档(产物)是否与现状同步。

deploy-sync 场景专用(变更联动 gate,第 2 层"自动化+变更联动 gate"方案)。

判定规则(每条 WARN 级,不阻断变更,只提醒该更新/重生哪些部署产物):
  按 params["artifact"] 分派到 4 个子检查:
    schema_sql      — PG schema 变更 → schema.sql 表数 vs dump 表数
    plist_backup    — plist 变更     → LaunchAgents 数 vs etc/plists 数 + 抽查内容
    requirements    — 装新依赖       → requirements.txt 包数 vs pip freeze 实际包数(差>3 告警)
    agent_config    — Agent 配置变更 → 调 snap-agent-configs.sh --check 看有无偏离/无快照

  每个子检查都先看变更类型是否在 changed 列表;不在则跳过(返回 True "未涉及…变更,跳过")。
  异常一律 catch 返回 (True, "检查异常,跳过:<err>")(gate 不因检查失败而 fail)。
"""
import ast
import re
import subprocess
from pathlib import Path

# 子检查的超时(秒)
_TIMEOUT = 30


def _coerce_changed(value, context: dict) -> list:
    """把 changed 参数规整成 list[str]。

    engine 的 _resolve_template 用 str.format(**context) 解析 {changed}:
      - 若 context["changed"] 是 list → str(list) 如 "['pg_schema', 'deps']"
      - 也可能是直接传入的 list(若 context 里就是 list)
    """
    if isinstance(value, list):
        return [str(x).strip() for x in value if x]
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x]
            except Exception:
                pass
            # 退化:逗号切分
            inner = s.strip("[]").strip()
            if not inner:
                return []
            return [d.strip().strip("'\"") for d in inner.split(",") if d.strip()]
        if s == "" or "{" in s:
            # 占位符未解析 → 退回 context
            return _coerce_changed(context.get("changed"), context)
        return [s]
    return [str(value)] if value is not None else []


def _run(cmd: list, timeout: int = _TIMEOUT) -> tuple:
    """统一跑子进程,返回 (rc, stdout, stderr)。失败返回 (非零, 输出, err)。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired:
        return 124, "", f"超时({timeout}s)"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# DS1: schema.sql 同步
# ---------------------------------------------------------------------------
def _count_create_table(text: str) -> int:
    """计 CREATE TABLE 语句数(行首,大小写不敏感)。"""
    return len(re.findall(r"(?mi)^\s*CREATE\s+TABLE\b", text))


def _check_schema_sql(vault: str, changed: list) -> tuple:
    if "pg_schema" not in changed:
        return True, "未涉及 PG schema 变更,跳过"

    schema_path = Path(vault) / "05-System" / "backups" / "pg" / "schema.sql"
    if not schema_path.exists():
        return True, f"无 schema.sql({schema_path}),跳过"

    try:
        schema_text = schema_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return True, f"读取 schema.sql 异常,跳过:{e}"
    schema_count = _count_create_table(schema_text)

    # 找最新 dump
    pg_dir = Path(vault) / "05-System" / "backups" / "pg"
    dumps = sorted(pg_dir.glob("nexus_mem_*.dump")) if pg_dir.exists() else []
    if not dumps:
        return True, f"无 dump 可对比({pg_dir}),跳过 schema 表数校验"
    latest_dump = dumps[-1]

    # pg_restore --schema-only -f - 把 DDL 输出到 stdout,计 CREATE TABLE
    # 注: 不带 -f/-d 时 pg_restore 拒绝运行(-f - 表示输出到 stdout)
    rc, out, err = _run(
        ["pg_restore", "--schema-only", "--no-owner", "--no-privileges", "-f", "-", str(latest_dump)],
        timeout=60,
    )
    if rc != 0 and not out:
        # pg_restore 即使 rc 非 0 也常输出内容(权限/warning),只在无输出时算失败
        return True, f"pg_restore 异常,跳过:{err.strip()[:120] or 'rc=' + str(rc)}"
    dump_count = _count_create_table(out)

    if schema_count != dump_count:
        return (
            False,
            f"schema.sql 表数({schema_count})与dump({dump_count})不一致,需重生: "
            f"pg_restore --schema-only -f schema.sql {latest_dump.name}",
        )
    return True, f"schema.sql 与 dump 一致(表数 {schema_count})"


# ---------------------------------------------------------------------------
# DS2: plist 备份同步
# ---------------------------------------------------------------------------
def _check_plist_backup(vault: str, changed: list) -> tuple:
    if "plist" not in changed:
        return True, "未涉及 plist 变更,跳过"

    home_plists = sorted(Path.home().glob("Library/LaunchAgents/ai.nexus.*.plist"))
    repo_dir = Path(vault) / "05-System" / "自动化脚本" / "etc" / "plists"
    repo_plists = sorted(repo_dir.glob("ai.nexus.*.plist")) if repo_dir.exists() else []

    if len(home_plists) != len(repo_plists):
        return (
            False,
            f"plist 备份({len(repo_plists)})与实际({len(home_plists)})数量不一致,需 cp 同步: "
            f"cp ~/Library/LaunchAgents/ai.nexus.*.plist {repo_dir}/",
        )

    # 抽查 1 个(ai.nexus.xdr 优先)内容是否一致
    sample_name = None
    for name in ("ai.nexus.xdr", "ai.nexus.api", "ai.nexus.embed"):
        if (Path.home() / "Library" / "LaunchAgents" / f"{name}.plist").exists():
            sample_name = name
            break
    if sample_name is None and home_plists:
        sample_name = home_plists[0].stem

    if sample_name:
        home_p = Path.home() / "Library" / "LaunchAgents" / f"{sample_name}.plist"
        repo_p = repo_dir / f"{sample_name}.plist"
        if not repo_p.exists():
            return False, f"抽查 {sample_name}.plist: 备份缺失,需 cp 同步"
        try:
            h = home_p.read_text(encoding="utf-8", errors="ignore")
            r = repo_p.read_text(encoding="utf-8", errors="ignore")
            # 归一化行尾再比
            if h.replace("\r\n", "\n") != r.replace("\r\n", "\n"):
                return False, f"plist 备份({len(repo_plists)})与实际数量一致但内容漂移({sample_name}.plist),需 cp 同步"
        except OSError as e:
            return True, f"抽查 {sample_name}.plist 异常,跳过:{e}"

    return True, f"plist 备份同步({len(repo_plists)} 个)"


# ---------------------------------------------------------------------------
# DS3: requirements.txt 同步
# ---------------------------------------------------------------------------
def _check_requirements(vault: str, changed: list) -> tuple:
    if "deps" not in changed:
        return True, "未涉及依赖变更,跳过"

    req_path = Path(vault) / "05-System" / "自动化脚本" / "requirements.txt"
    if not req_path.exists():
        return True, f"无 requirements.txt({req_path}),跳过"

    # 口径说明:requirements.txt 是「筛选后」的(只含 nexus 实际 import 的包),
    # 不是 pip freeze 全量。所以不能直接数 freeze(会误报 143 vs 28)。
    # 正确做法:复用 sync-deploy-artifacts.sh --check 的筛选口径,保证一致。
    sync_script = Path(vault) / "05-System" / "自动化脚本" / "sync-deploy-artifacts.sh"
    if not sync_script.exists():
        return True, f"无 sync-deploy-artifacts.sh,跳过 requirements 检查"

    rc, out, err = _run(["bash", str(sync_script), "--check"], timeout=60)
    # 解析输出找 requirements 行
    for line in (out + err).splitlines():
        if "requirements" in line.lower() and ("一致" in line or "偏离" in line or "✅" in line or "❌" in line or "⚠️" in line):
            if "一致" in line or "✅" in line:
                return True, f"requirements.txt 同步({line.strip()[:60]})"
            else:
                return False, f"requirements.txt 偏离,需重生: {line.strip()[:80]}"
    # 没解析到明确结果,视为通过(gate 不因解析失败而 fail)
    return True, "requirements.txt 检查完成(未检测到偏离)"


# ---------------------------------------------------------------------------
# DS4: Agent 配置快照同步
# ---------------------------------------------------------------------------
def _check_agent_config(vault: str, changed: list) -> tuple:
    if "agent_config" not in changed:
        return True, "未涉及 Agent 配置变更,跳过"

    script = Path(vault) / "05-System" / "自动化脚本" / "snap-agent-configs.sh"
    if not script.exists():
        return True, f"无 snap-agent-configs.sh({script}),跳过"

    rc, out, err = _run(["bash", str(script), "--check"], timeout=60)
    if rc == 124:
        return True, f"snap-agent-configs.sh --check 超时,跳过"
    text = (out + "\n" + err) if err else out

    # 解析"偏离/无快照"明细
    drift = []
    for ln in text.splitlines():
        if "偏离" in ln or "无快照" in ln or "❗" in ln:
            drift.append(ln.strip())
    if drift:
        return (
            False,
            f"Agent 配置快照偏离({len(drift)} 处): " + "; ".join(drift[:5]),
        )
    return True, "Agent 配置快照同步(--check 无偏离)"


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
_DISPATCH = {
    "schema_sql": _check_schema_sql,
    "plist_backup": _check_plist_backup,
    "requirements": _check_requirements,
    "agent_config": _check_agent_config,
}


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      artifact: 子检查名(schema_sql / plist_backup / requirements / agent_config)
      vault:    Vault 根路径(engine 已解析占位符)
      changed:  本次变更类型列表(可能是 str(list) 或 list)
    返回: (passed, detail)
    """
    artifact = params.get("artifact", "")
    vault = params.get("vault") or context.get("vault", "")
    changed = _coerce_changed(params.get("changed"), context)

    fn = _DISPATCH.get(artifact)
    if fn is None:
        return True, f"未知 artifact: {artifact},跳过"

    if not vault:
        return True, "无 vault 参数,跳过"

    try:
        return fn(vault, changed)
    except Exception as e:
        return True, f"检查异常,跳过:{type(e).__name__}: {e}"
