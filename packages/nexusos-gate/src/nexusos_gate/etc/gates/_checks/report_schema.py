"""检查类型: report_schema — report.md 尾部机读状态块检查（Task597 #48）。

2611111749 宽容化重写（池 #826②，severity 已是 REJECT——Task1993）。红队
实测（task/2611111748）：近 20 单 15 单带 REJECT 级警告仍 completed，G12
最频，相当部分是假 REJECT 三坑：
  a) 块合法但缺 NEXUS 标记行 → 旧版按「标记在围栏内」过滤围栏，误报缺块
  b) 标记行写在围栏外 → 围栏内容匹配不到标记，同上误报
  c) status: done（旧枚举 {complete,blocked,continue} 外）→ 语义=complete，
     误报「status 非法」
修法遵 #574 D 家族元诊断：语义宽容 + 报错精准——识别降级到「```yaml 围栏
内含 status 行」（NEXUS 标记行不再强制、位置不限），枚举收编同义词；失败
时 detail 必须指出具体缺哪项（围栏/status/取值/next_steps 分开报）。
围栏方言仍是契约：必须 ```yaml——裸 ```/```json 等即使带标记行+status
也拦（e2e 对抗基线 g12-non-yaml-fence 锁死，宽容止于三坑不越界）。
"""
import os
import re
from pathlib import Path

try:
    import _vaultlink
except ImportError:
    from . import _vaultlink

_STATUS_RE = re.compile(r"^\s*status:\s*(.+?)\s*$", re.MULTILINE)
_NEXT_INLINE_RE = re.compile(r"^\s*next_steps:\s*(\[.*?\]|\S.+)$", re.MULTILINE)
_NEXT_KEY_RE = re.compile(r"^\s*next_steps:\s*$", re.MULTILINE)

# 同义词收编：写法变体不改语义（done 就是 complete）。语义宽容不等于不设限
# ——完全无法识别的取值仍拦（detail 报原值+合法值域，防「随便写都过」）。
_FINISHED = {"complete", "done", "finished", "ok"}
_UNFINISHED = {"continue", "blocked", "in_progress", "in-progress", "pending", "wip", "todo"}
_VALID_HINT = ("完成态 complete/done/finished/ok；"
               "未完态 continue/blocked/in_progress/pending/wip/todo（须带 next_steps）")


def _norm(raw: str) -> str:
    """取值归一：去装饰字符、小写、完成态同义词收编（done=complete）。"""
    s = raw.strip().strip("!！。.").lower()
    return "complete" if s in _FINISHED else s


def _has_next_steps(block: str) -> bool:
    """next_steps 非空：同行取值（[...] 或标量）或多行列表（后续 - 项）。"""
    m = _NEXT_INLINE_RE.search(block)
    if m and m.group(1).strip() not in ("[]", "[ ]"):
        return True
    km = _NEXT_KEY_RE.search(block)
    if km:
        for line in block[km.end():].split("\n"):
            s = line.strip()
            if not s:
                continue
            if s.startswith("- ") and len(s) > 2:
                return True
            break  # 首个非列表行即止（后续 yaml 字段不算 next_steps 内容）
    return False


def _fenced_blocks_with_end(text: str) -> list:
    """带结束位置的行级围栏遍历（B7，池#826）。

    语义与 _vaultlink.split_fences 同源（同 _FENCE_LINE_RE、未闭合剥到文末），
    额外产出每块结束字符 offset（闭栏行/文末之后的 pos）——供「机读块在尾部
    窗口内」判定：先全文配对后验位，替代旧法先截尾（窗口起点切进围栏体时
    开栏丢失、后续配对全移位——B5 report 4180 字符三轮 G12 误报实测）。
    注意：split_fences 若改围栏语义，本函数须同步（同一正则同一行循环）。
    """
    out, buf, info, pos = [], None, "", 0
    for line in text.split("\n"):
        pos += len(line) + 1
        m = _vaultlink._FENCE_LINE_RE.match(line)
        if m:
            if buf is None:
                info, buf = m.group(2).strip(), []
            else:
                out.append((info, "\n".join(buf), pos))
                buf, info = None, ""
        elif buf is not None:
            buf.append(line)
    if buf is not None:
        out.append((info, "\n".join(buf), pos))
    return out


def check(params: dict, context: dict, agent: str) -> tuple:
    """
    params:
      path: report.md 路径（{task_path_report} 占位符，engine 已解析）
    返回: (passed, detail) — REJECT/WARN 级由 yaml severity 控制
    """
    path = params.get("path", "")
    if not path or "{" in path:
        # 同 line_count Task532 P-g3：可选字段缺失 fail-open 跳过
        return True, "task_path_report 未提供（可选字段），跳过 report_schema 检查"
    path = str(Path(path).expanduser())
    if not os.path.exists(path):
        return True, f"report.md 不存在（{path[:60]}），跳过 report_schema 检查"

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError as e:
        return False, f"读取失败: {path} ({e})"

    # 只看尾部（最后 3000 字符足够容纳状态块，防正文误命中）——B7：先全文
    # 配对后验窗口（旧法 text[-3000:] 截尾先行，窗口切进围栏体即配对错乱）。
    blocks = _fenced_blocks_with_end(text)
    yaml_blocks = [(c, end) for i, c, end in blocks if i == "yaml"]
    if not yaml_blocks:
        return False, ("report.md 尾部缺机读状态块——无 ```yaml 围栏"
                       "（Task597 #48：尾部加 ```yaml 围栏含 status/evidence/"
                       "next_steps，模板见 task-spec §2 第 6 项；非 yaml 围栏"
                       "（如裸 ```）不算机读块）")
    candidates = [x for x in yaml_blocks if _STATUS_RE.search(x[0])]
    if not candidates:
        return False, ("机读块缺 status 字段——```yaml 围栏存在但不含 "
                       "status 行（模板见 task-spec §2 第 6 项）")

    # 多候选（正文示例 yaml + 尾部真块）时优先 status 可识别的最后一个
    def _st(item):
        return _norm(_STATUS_RE.search(item[0]).group(1))

    recognized = [x for x in candidates if _st(x) in _UNFINISHED | {"complete"}]
    block, block_end = (recognized or candidates)[-1]
    # 窗口判定（陷阱3：块结束 offset ≥ len-3000 为内，边界值算内）
    if block_end < len(text) - 3000:
        return False, (f"机读块不在尾部窗口（块结束 offset {block_end}，"
                       f"窗口起点 {len(text) - 3000}）——机读块必须在 report "
                       "尾部（防正文中部示例块误命中）")
    raw = _STATUS_RE.search(block).group(1).strip()
    status = _norm(raw)
    if status not in _UNFINISHED | {"complete"}:
        return False, f"机读块 status 无法识别: {raw}（合法: {_VALID_HINT}）"
    if status != "complete" and not _has_next_steps(block):
        return False, (f"status={raw} 属未完成态，next_steps 必填且非空"
                       "（同行 [...] 取值或后续 - 列表项均可）")
    return True, f"机读块合法（status={raw}）"
