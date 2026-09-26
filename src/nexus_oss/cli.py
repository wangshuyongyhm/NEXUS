"""nexus — NEXUS CLI（骨架期最小入口）。

- `nexus setup`：本地 Web 配置向导（key → ~/.nexus/.env，真值不进仓库）
- `nexus providers`：列出 Provider 注册表与 dispatch-ready 状态（调度层可见性）
"""
import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["setup"]:
        from nexus_oss.setup_wizard import run
        return run(argv[1] if len(argv) > 1 else "")
    if argv[:1] == ["providers"]:
        from nexus_oss.providers import configured_providers
        rows = configured_providers()
        print(f"{'id':<14} {'ready':<7} {'来源':<6} label")
        for r in rows:
            src = "内置" if r["builtin"] else "自定义"
            print(f"{r['id']:<14} {'✅' if r['ready'] else '—':<7} {src:<6} {r['label']}"
                  + (f"（缺 {', '.join(r['missing'])}）" if r["missing"] else ""))
        ready = sum(1 for r in rows if r["ready"])
        print(f"\n{ready}/{len(rows)} 平台 dispatch-ready"
              f"（注册表: NEXUS_AGENT_PROVIDERS，向导 `nexus setup` 可增删）")
        return 0
    print("usage: nexus setup [env_file_path] | nexus providers")
    return 2


if __name__ == "__main__":
    sys.exit(main())
