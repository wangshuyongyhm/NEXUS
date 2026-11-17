#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_tokens_zh.py — task/1452 存量知识 tokens_zh 回填（幂等/断点续跑）。

1449 施工草稿 §2.4：按 id 升序分批（默认 2000 条/批），SELECT id,title,content
→ jieba 分词（与写入侧同源 tokenize_for_write，强制 flag 语境）→ UPDATE tokens_zh
（generated 列 search_vector_zh 自动重算）。WHERE tokens_zh IS NULL 跳过已回填，
中断可续跑。范围=活跃行（superseded_by IS NULL AND COALESCE(deprecated,FALSE)=FALSE）
——废弃行不进检索，回填无收益（草稿 §2.4 范围裁定）。

用法：
  python3 backfill_tokens_zh.py --limit 100    # 抽样验证
  python3 backfill_tokens_zh.py                # 全量（35078 条）
  python3 backfill_tokens_zh.py --report-only  # 只出分布对账不改库
"""
import argparse
import os
import sys
import time
from collections import Counter

# 回填必须真分词：无视外部 flag 语境强制 on（脚本本身即 flag-on 行为的落地）
os.environ["NEXUS_FTS_JIEBA"] = "1"

import psycopg2  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from nexusos_mem.tokenize_zh import tokenize_for_write, _lcut_join  # noqa: E402

BATCH = 2000


def fetch_batch(cur, limit):
    cur.execute(
        "SELECT id, title, content FROM knowledge "
        "WHERE tokens_zh IS NULL AND superseded_by IS NULL "
        "  AND COALESCE(deprecated, FALSE) = FALSE "
        "ORDER BY id LIMIT %s",
        (limit,),
    )
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只回填前 N 条（0=全量）")
    ap.add_argument("--batch", type=int, default=BATCH, help="批大小")
    ap.add_argument("--report-only", action="store_true", help="只出分布对账")
    args = ap.parse_args()

    conn = psycopg2.connect("dbname=nexus_mem")
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT count(*) FROM knowledge WHERE tokens_zh IS NULL "
        "AND superseded_by IS NULL AND COALESCE(deprecated, FALSE) = FALSE"
    )
    pending = cur.fetchone()[0]
    print(f"[INFO] 待回填活跃行: {pending}")

    if args.report_only:
        conn.rollback()
        conn.close()
        return

    # 预热词典（首批 1s 加载摊平）
    _lcut_join("预热")

    t0 = time.time()
    done = skipped = 0
    remaining = args.limit if args.limit > 0 else pending
    while remaining > 0:
        rows = fetch_batch(cur, min(args.batch, remaining))
        if not rows:
            break
        for kid, title, content in rows:
            tok = tokenize_for_write(title or "", content or "")
            # tok=None 仅当 title+content 全空——分词函数已 fail-open，此处兜底空串
            cur.execute(
                "UPDATE knowledge SET tokens_zh = %s WHERE id = %s",
                (tok or "", kid),
            )
            done += 1
        conn.commit()
        remaining -= len(rows)
        rate = done / max(time.time() - t0, 0.001)
        print(f"[PROG] {done} rows | {rate:.0f} rows/s | 剩余 {remaining}")

    elapsed = time.time() - t0

    # ---- 分布对账（陷阱4：fts_score 分布漂移影响 0.5/0.5 权重切换）----
    cur.execute(
        "SELECT count(*) FROM knowledge WHERE tokens_zh IS NULL "
        "AND superseded_by IS NULL AND COALESCE(deprecated, FALSE) = FALSE"
    )
    left = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM knowledge WHERE tokens_zh IS NOT NULL AND tokens_zh != ''")
    filled = cur.fetchone()[0]
    cur.execute(
        "SELECT coalesce(array_length(string_to_array(tokens_zh, ' '), 1), 0) AS n "
        "FROM knowledge WHERE tokens_zh IS NOT NULL AND tokens_zh != '' "
        "ORDER BY random() LIMIT 500"
    )
    lens = [r[0] for r in cur.fetchall()]
    conn.commit()
    conn.close()

    stats = {
        "backfilled": done,
        "pending_after": left,
        "nonempty_tokens_rows": filled,
        "elapsed_sec": round(elapsed, 1),
        "rate_rows_per_s": round(done / max(elapsed, 0.001), 1),
        "sampled_token_len": {
            "n": len(lens),
            "min": min(lens) if lens else 0,
            "median": sorted(lens)[len(lens) // 2] if lens else 0,
            "max": max(lens) if lens else 0,
        },
    }
    print("[STATS]", stats)
    if done > 0:
        print(f"[OK] 回填 {done} 条 / {elapsed:.0f}s；活跃行剩余 NULL：{left}（0=全量完成）")


if __name__ == "__main__":
    main()
