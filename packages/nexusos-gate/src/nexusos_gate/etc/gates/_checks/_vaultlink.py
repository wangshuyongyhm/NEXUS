"""_vaultlink.py — Vault wikilink 共享解析器（Task592，D6/G11 插件共用）。

不做插件（下划线前缀被 gate_engine 加载器跳过），纯函数库：
  - strip_code_blocks: 剥离 ``` 围栏代码块（Tb_user 数组污染统计的教训，任务书§7）
  - extract_wikilinks: 提取 [[target|alias]] / [[target#heading]] 的 target
  - resolve_target: 锚存在性校验——路径优先（VAULT_ROOT/target[.md] 或目录），
    失败再 basename 全库索引（对齐 Obsidian 解析规则，任务书§7）

basename 索引进程级缓存（构建一次 ~2s，dispatch/done gate 复用）。
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_VAULT_ROOT = None
_BNAME_INDEX = None  # {basename_lower: [abs_path, ...]}

# Task592 宽限：08-19 上线首日 WARN 放行，08-20 00:00 UTC 起自动切 REJECT（免人工改 yaml）
GRACE_END = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)


def vault_root() -> Path:
    global _VAULT_ROOT
    if _VAULT_ROOT is None:
        env = os.environ.get("NEXUS_VAULT_ROOT", "")
        _VAULT_ROOT = Path(env) if env else Path(__file__).resolve().parents[9]
    return _VAULT_ROOT


def reset_cache():
    """测试用：清缓存（tmp vault 场景）。"""
    global _VAULT_ROOT, _BNAME_INDEX
    _VAULT_ROOT = None
    _BNAME_INDEX = None


def in_grace() -> bool:
    # 统一 aware（naive vs aware 不可比较——首版 GRACE_END 朴素值被 mock 测试打爆）
    return datetime.now(timezone.utc) < GRACE_END


_FENCE_LINE_RE = re.compile(r"^\s{0,3}(`{3,})([^`]*)$")


def split_fences(text: str) -> tuple:
    """行级围栏解析（池 #826③ 修法核心，CommonMark 围栏语义）。

    返回 (kept_text, blocks)：kept=围栏外文本，blocks=[(info, content)]。
    围栏标记 = 整行只有 3+ 反引号（开栏可跟无反引号 info 串如 ```yaml，
    闭栏仅空白尾随）。行内 ``` 提及（正文写「尾部加 ```yaml 围栏」）不是
    围栏——旧 DOTALL 正则把它当开栏、误剥到下一个反引号，后续 wikilink
    被吞 → G14 子图连通假 REJECT（红队 task/2611111748 实测）。未闭合
    围栏剥到文末（Obsidian 渲染语义，Task1301 缺口2 保持）。
    """
    kept, blocks, buf, info = [], [], None, ""
    for line in text.split("\n"):
        m = _FENCE_LINE_RE.match(line)
        if m:
            if buf is None:
                info = m.group(2).strip()
                buf = []
            else:
                blocks.append((info, "\n".join(buf)))
                buf, info = None, ""
            continue
        if buf is None:
            kept.append(line)
        else:
            buf.append(line)
    if buf is not None:  # 未闭合围栏：到文末都是代码
        blocks.append((info, "\n".join(buf)))
    return "\n".join(kept), blocks


def strip_code_blocks(text: str) -> str:
    """剥离围栏代码块 + 行内 code span（块内 [[ 是数据不是链接）。

    围栏剥离走 split_fences 行级解析（围栏语义见 #826③ 说明）。围栏外
    再做行内剥离，配对规则：
    - 同行等长 N≥2 配对（``x``、单行 ```x``` 字面量）——跨行不配：
      两个行内 ``` 提及跨行配对会重演 #826③ 误剥，宁保留文本（链接
      可被检查，D 家族宁漏勿滥方向）。
    - 单反引号配对（Task592 清偿；Task1301 放宽跨行——CommonMark code
      span 渲染为空格）；落单奇数反引号=语法残缺，按普通文本保持提取。
    """
    kept, _ = split_fences(text)
    kept = re.sub(r"(?<!`)(`{2,})([^`\n]*?)\1(?!`)", "", kept)
    return re.sub(r"(?<!`)`([^`]+)`(?!`)", "", kept)


_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")


def extract_wikilinks(text: str, strip_code: bool = True) -> list:
    """提取 [[target|alias]] / [[target#sec]] / [[target#^block]] 的 target 列表。

    跳过空 target；embed 前缀 ! 不影响（正则从 [[ 起）。http(s) 链接不带 [[ 不会命中。
    """
    if strip_code:
        text = strip_code_blocks(text)
    out = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).split("|")[0].split("#")[0].strip()
        if target:
            out.append(target)
    return out


def _build_bname_index() -> dict:
    idx = {}
    for p in vault_root().rglob("*.md"):
        # Task1541: 排除 worktree 目录——git worktree 是主库文件的完整副本
        # （小弟 D8 施工期间 nexus-wt* 内存在同名 .md），不排除则任何裸名锚
        # 双命中=歧义断链（1541 派发时 D6 实锤）。.wt/ 同族（1524 先例）。
        parts = p.parts
        if any(seg.startswith("nexus-wt") or seg == ".wt" for seg in parts):
            continue
        idx.setdefault(p.name.lower(), []).append(p)
    return idx


def resolve_target(target: str) -> bool:
    """锚存在性：路径解析（.md 文件或目录）优先，basename 全库索引兜底。"""
    root = vault_root()
    t = target.strip().strip('"')
    # 路径解析：绝对相对 VAULT_ROOT（带/不带 .md；目录也认——上级任务锚 task/NN）
    cand = root / t
    if cand.is_dir() or cand.is_file():
        return True
    if not t.endswith(".md"):
        if (root / (t + ".md")).is_file():
            return True
    # basename 解析（Obsidian 规则：任意目录同名笔记均可解析）
    global _BNAME_INDEX
    if _BNAME_INDEX is None:
        try:
            _BNAME_INDEX = _build_bname_index()
        except Exception:
            return True  # 索引构建失败 fail-open（宁漏勿滥）
    name = t if t.endswith(".md") else t + ".md"
    hits = _BNAME_INDEX.get(name.lower())
    # 1401-d1：短名仅唯一命中才解析——歧义（vault 内重名，如 task 域
    # full-log.md ×2000+）仍报断链。Obsidian 对重名裸链本就需全路径消歧，
    # 短名不可靠指向；宁拦勿放（fail-closed，歧义是作者该修的债）。
    return bool(hits) and len(hits) == 1
