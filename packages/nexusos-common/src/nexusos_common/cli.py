"""nexusos_common.cli — `nexus` 命令入口（1965，spec §0 CLI 层）。

子命令：init（[--scan|--doctor]）、setup（别名提示）。--json 全自动路径
（无交互——禁必须 TTY）；交互三选仅在显式 TTY 且未给选择 flag 时出现。
"""
from __future__ import annotations

import argparse
import json
import sys

from nexusos_common import __version__


def _emit(payload: dict, as_json: bool):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def cmd_scan(args) -> int:
    from nexusos_common.wizard import scan as scan_mod
    result = scan_mod.scan_all(pg_dsn=args.pg_dsn, macos_perms=args.macos_perms)
    _emit({"phase": "scan", **result}, args.json)
    if not args.json:
        print(scan_mod.render_table(result))
    blockers = result["summary"]["blockers"]
    return 1 if blockers else 0


def cmd_doctor(args) -> int:
    from nexusos_common.wizard import doctor as doctor_mod
    result = doctor_mod.doctor(pg_dsn=args.pg_dsn, macos_perms=args.macos_perms)
    _emit({"phase": "doctor", **result}, args.json)
    if not args.json:
        print(doctor_mod.render(result))
    return 0 if result["all_green"] else 1


def _ask(prompt: str, choices: tuple[str, ...], default: str) -> str:
    """交互三选（仅 TTY 路径；非 TTY 一律回落 default——LOOP 最小风险默认）。"""
    if not sys.stdin.isatty():
        return default
    while True:
        ans = input(f"{prompt} [{'/'.join(choices)}]（默认 {default}）: ").strip().lower() or default
        if ans in choices:
            return ans
        print(f"请输入 {' / '.join(choices)}")


def cmd_init(args) -> int:
    from nexusos_common import nexus_home
    from nexusos_common.wizard import config as cfg
    from nexusos_common.wizard import provision as prov
    from nexusos_common.wizard import scan as scan_mod

    # ---- Phase 1 扫描 ----
    scan = scan_mod.scan_all(pg_dsn=args.pg_dsn, macos_perms=args.macos_perms)
    if scan["summary"]["blockers"]:
        _emit({"phase": "init", "ok": False, "reason": "环境阻断（先解阻断项）",
               "scan": scan}, args.json)
        if not args.json:
            print(scan_mod.render_table(scan))
            print("\n❌ 阻断项在案——解阻断后重跑（.nexus 可写/Python≥3.11/受支持 OS）")
        return 2

    # ---- Phase 2 三选协商（flag > env 提示 > 交互 > 推荐默认） ----
    vault_choice = args.vault or _ask(
        "vault 方案：A=指向已有 Markdown 目录 / B=生成 starter vault（推荐）/ C=跳过降级",
        ("a", "b", "c"), "b")
    pg_choice = args.pg or _ask(
        "PG 方案：A=Docker 片段（自执行）/ B=已有 PG 建专属库 / C=xdr-only 降级",
        ("a", "b", "c"), "b" if scan["checks"][2]["ok"] else "a")

    port_rows = scan["checks"][3]["ports"]  # probe_ports 平铺键（_check extra 展开）
    ports = {n: row["port"] for n, row in port_rows.items()}
    conflicts = {n: row["port"] for n, row in port_rows.items() if not row["free"]}
    realloc = {}
    if conflicts:
        realloc = prov.allocate_ports(conflicts)
        for n, p in realloc.items():
            ports[n] = p

    provision_result = None
    dsn_for_env = "none"
    if pg_choice == "a":
        provision_result = {"applied": False, "ok": True,
                            "detail": "A 通道：Docker compose 片段已输出（spec：不替跑 docker）"}
    elif pg_choice == "b":
        dsn = args.pg_dsn or "postgresql://localhost/postgres"
        provision_result = prov.provision_existing_pg(dsn, dbname=args.pg_dbname, run=not args.dry_run)
        dsn_for_env = prov._rebase_dsn(dsn, args.pg_dbname)  # 角色密码不进 .env DSN（最小权限：应用层另配）
    else:
        provision_result = {"applied": False, "ok": True,
                            "detail": "C 通道降级：损失清单——" + "；".join(prov.DEGRADE_LOSSES)}
        dsn_for_env = "none"

    # ---- Phase 3 配置生成（幂等） ----
    home = nexus_home()
    env_result = cfg.write_env(ports, dsn_for_env, home=home, force=args.force)
    vault_result = {"path": "", "created": [], "detail": "C 通道：跳过（constraint 层降级）"}
    if vault_choice == "b":
        vault_dir = home / "vault-starter"
        vault_result = cfg.write_starter_vault(vault_dir)
    elif vault_choice == "a":
        target = args.vault_dir
        if target:
            vault_result = {"path": target, "created": [],
                            "detail": f"A 通道：用户指向 {target}（向导不写用户目录）"}
        else:
            vault_result = {"path": "(未提供 --vault-dir)", "created": [],
                            "detail": "A 通道缺 --vault-dir——未落盘（重跑补参）"}
    agent_reg = cfg.write_agent_registration(
        [{"id": a["id"], "name": a["name"], "found_via": a["found_via"]} for a in scan["agents"]], home)

    if pg_choice == "a" and not args.json:
        print(prov.docker_snippet())

    report = cfg.render_report(env_result, vault_result, agent_reg, provision_result, realloc)
    _emit({"phase": "init", "ok": True,
           "choices": {"vault": vault_choice, "pg": pg_choice},
           "scan": scan, "env": env_result, "vault": vault_result,
           "provision": {k: v for k, v in (provision_result or {}).items() if k != "app_role_password"},
           "ports_reallocated": realloc, "agents": agent_reg}, args.json)
    if not args.json:
        print(scan_mod.render_table(scan))
        print()
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    from nexusos_common import update_check
    update_check.cli_notify(argv)  # 1970 启动提示（stderr 一行；缓存读零阻塞+后台刷新）
    ap = argparse.ArgumentParser(prog="nexus", description="NEXUS 初始化向导 CLI（spec v1）")
    ap.add_argument("--version", action="version", version=f"nexusos-common {__version__}")
    ap.add_argument("--no-check", action="store_true",
                    help="禁用启动更新提示（等价 NEXUS_UPDATE_FEED=off，本次运行不联网）")
    sub = ap.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="初始化向导（scan→协商→配置→报告；幂等）")
    p_init.add_argument("--scan", action="store_true", help="仅 Phase1 环境扫描（只读）")
    p_init.add_argument("--doctor", action="store_true", help="幂等复检（对账不重写）")
    p_init.add_argument("--json", action="store_true", help="机器输出（Agent 层消费，无交互）")
    p_init.add_argument("--pg-dsn", default=None, help="PG 管理连接串（默认 postgresql://localhost/postgres）")
    p_init.add_argument("--pg-dbname", default="nexus_mem", help="nexus 专属库名（默认 nexus_mem）")
    p_init.add_argument("--vault", choices=("a", "b", "c"), default=None, help="vault 三选（缺省交互/推荐 B）")
    p_init.add_argument("--vault-dir", default=None, help="A 通道：用户已有 Markdown 目录")
    p_init.add_argument("--pg", choices=("a", "b", "c"), default=None, help="PG 三选（缺省交互/推荐 B）")
    p_init.add_argument("--macos-perms", action="store_true", help="检查 macOS TCC 权限（仅 OCRX 启用时——spec 陷阱）")
    p_init.add_argument("--force", action="store_true", help="覆盖重写 .env（默认幂等不覆盖）")
    p_init.add_argument("--dry-run", action="store_true", help="置备只出 plan 不执行")
    p_init.set_defaults(func=lambda a: cmd_scan(a) if a.scan else (cmd_doctor(a) if a.doctor else cmd_init(a)))

    p_setup = sub.add_parser("setup", help="（预留：组件安装=spec §6 生态闭环位）")
    p_setup.set_defaults(func=lambda a: (print("nexus setup=组件安装（另单）；向导请用 nexus init"), 0)[1])

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
