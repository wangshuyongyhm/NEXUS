"""检查类型: agent_version_synced — Agent 版本与 baseline 同步检查。

I6 用。调 check_agent_versions.sh 检测版本变化。
exit 0 = 一致, exit 1 = 不一致 → fail/REJECT 硬拦,强制主控更新 registry+baseline。
"""

# Task1597 参数化：vault 根经 env/仓内推导解析，不再硬编码本机路径
try:
    from _vault_root import vault_root
except ImportError:  # 包模式加载（gate_engine 以子包形态 import 时）
    from ._vault_root import vault_root

import os
import subprocess
from pathlib import Path


def _resolve_project_root(params: dict, context: dict) -> str:
    """取 project_root,优先 params > context > env-default 默认值。"""
    pr = params.get("project_root") or context.get("project_root") or ""
    if not pr or "{" in str(pr):
        pr = vault_root()
    return pr


def check(params: dict, context: dict, agent: str) -> tuple:
    """I6: Agent 版本同步检查。

    params(可选):
      project_root: Vault 根路径(默认 NEXUS_VAULT_ROOT 环境变量,未设时用内置字面值)
    返回: (passed: bool, detail: str)
    """
    project_root = _resolve_project_root(params, context)
    script = Path(project_root) / "05-System" / "自动化脚本" / "check_agent_versions.sh"

    try:
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return False, "check_agent_versions.sh 超时(30s)"
    except FileNotFoundError:
        return False, f"脚本不存在: {script}"
    except Exception as e:
        return False, f"执行异常: {type(e).__name__}: {str(e)[:100]}"

    stdout_tail = (result.stdout or "").strip()
    stderr_snippet = (result.stderr or "").strip()[:200]

    if result.returncode == 0:
        return True, "所有 Agent 版本与 baseline 一致"

    detail = "Agent 版本不一致（需更新 registry+baseline）"
    if stdout_tail:
        # 取末尾 300 字符（check_agent_versions.sh 输出末尾是变化摘要）
        detail += f"\n{stdout_tail[-300:]}"
    if stderr_snippet:
        detail += f"\nstderr: {stderr_snippet}"
    return False, detail
