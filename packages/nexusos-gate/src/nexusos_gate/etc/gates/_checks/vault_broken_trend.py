"""检查类型: vault_broken_trend — persist 时断链趋势对比。

P11: persist 时扫描当前断链数，与上次 persist 的基线对比，增长超阈值(+30)则 WARN。
把「累积几个会话大整理」变成「每会话微量发现」(MEM#46758)。

设计取舍：check 有副作用(append 当前到基线 history)，用 os.replace 原子写。
"""

# Task1597 参数化：vault 根经 env/仓内推导解析，不再硬编码本机路径
try:
    from _vault_root import vault_root
except ImportError:  # 包模式加载（gate_engine 以子包形态 import 时）
    from ._vault_root import vault_root

import os
import json
import time
import subprocess


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      baseline_path: 基线文件路径(vault-health.json)
      max_increase: 允许的最大断链增长数(默认 30)
      vault_root: vault 根目录
    返回: (passed, detail)
    """
    VAULT = params.get("vault_root") or vault_root()
    # Task1613: 落盘路径 env 可重定向——测试/套件引 persist gate 时不得写脏 tracked 基线
    # （vault-health.json 是滚动基线；被测试写入会让工作树变脏、worktree merge 被挡）。
    # 优先级 env > yaml 参数 > 默认：测试显式重定向到 tmp，生产路径与语义不变。
    baseline_path = (os.environ.get("NEXUS_VAULT_HEALTH_JSON")
                     or params.get("baseline_path", "05-System/自动化脚本/vault-health.json"))
    max_increase = int(params.get("max_increase", 30))

    if not os.path.isabs(baseline_path):
        baseline_path = os.path.join(VAULT, baseline_path)

    # 1. 读基线
    try:
        with open(baseline_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True, "P11 skip: 基线文件不存在或损坏"

    history = data.get("history", [])
    last_broken = history[-1].get("broken") if history else None

    # Task1539 提速: TTL 复用窗——最新扫描在 cache_ttl_s 内则复用其判定（跳过全库扫描）。
    # 语义权衡: 窗口内新引入的断链延后到下个窗口发现（WARN 级趋势检查，30min 粒度可接受；
    # 硬防线是 G11 产出零新断链 done gate，非本项）。cache_ttl_s=0 关闭复用。
    ttl_s = int(params.get("cache_ttl_s", 0) or 0)
    if ttl_s > 0 and history:
        try:
            last_ts = time.mktime(time.strptime(history[-1]["ts"], "%Y-%m-%dT%H:%M:%S"))
            age = time.time() - last_ts
            if age < ttl_s:
                if len(history) >= 2:
                    d = history[-1]["broken"] - history[-2]["broken"]
                    verdict = not (d > max_increase)
                    return verdict, (f"P11 TTL 复用({int(age//60)}min 前扫描,窗口{ttl_s//60}min): "
                                     f"broken {history[-2]['broken']}→{history[-1]['broken']} (Δ{d:+d})")
                return True, f"P11 TTL 复用({int(age//60)}min 前扫描,首条无对比)"
        except (KeyError, ValueError):
            pass  # ts 解析失败 → 走全量扫描

    # 2. 扫当前（EXCLUDE_DIRS 与 check_I2 一致）
    lib = f"{VAULT}/05-System/自动化脚本/nexus-monitor/checks/_lib/common.sh"
    # Task1539 提速: source_exclude_dirs(配置自 persist.yaml,1523 域模型机器域口径)——
    # 机器产物不作断链 source(快照时点链接非可维护信号,Task1299 修法A 泛化),
    # 跳过其内容读取(全库 .md 读取的 IO 大头)。by_name 保留=入链解析不变。
    exclude_arg = params.get("exclude_dirs", "05-System/NEXUS-MEM/coord-traces")
    src_excludes = params.get("source_exclude_dirs") or []
    env = dict(os.environ, SOURCE_EXCLUDE_DIRS=":".join(str(d) for d in src_excludes))
    script = f'source "{lib}"; scan_vault_wikilinks "{VAULT}" "{exclude_arg}"'
    try:
        r = subprocess.run(
            script, shell=True, capture_output=True, text=True,
            timeout=30, executable="/bin/bash", env=env,
        )
        cur = json.loads(r.stdout)
    except Exception as e:
        return True, f"P11 skip: 扫描异常 {e}"

    cur_broken = cur["broken_count"]
    cur_orphan = cur.get("orphan_count", 0)

    # 3. append 当前到 history（原子写，trim 到 last 50）
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    data.setdefault("history", []).append(
        {"ts": ts, "broken": cur_broken, "orphan": cur_orphan,
         "notes": cur.get("total_notes", 0)}
    )
    data["history"] = data["history"][-50:]
    data["last_check"] = ts
    tmp = baseline_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, baseline_path)

    # 4. 对比
    if last_broken is None:
        return True, f"P11 首次基线 broken={cur_broken}（无历史对比）"
    delta = cur_broken - last_broken
    if delta > max_increase:
        return False, (
            f"断链增长 {last_broken}→{cur_broken} (Δ+{delta} > {max_increase})，"
            f"检查本次 persist 是否引入断链（参考 MEM#46758）"
        )
    return True, f"断链趋势 OK {last_broken}→{cur_broken} (Δ{delta:+d})"
