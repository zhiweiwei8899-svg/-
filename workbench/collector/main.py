#!/usr/bin/env python3
"""采集器 CLI。

用法：
  python3 collector/main.py init-db
  python3 collector/main.py dump-raw --seconds 30     # 抓原始事件样本，用于修正字段映射
  python3 collector/main.py sync --seconds 60         # 拉事件 → 归一化 → 入库
  python3 collector/main.py stats
  python3 collector/main.py search --kw 预算 --limit 10

注意：
- 事件命令默认为 `dws event consume`，可用 --cmd 覆盖（dws 子命令可能随版本变化）。
- 首次真机运行请先 `dump-raw`，确认字段名后回填 collector/normalize.py 的 CANDIDATES。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import dws_client, normalize, store  # noqa: E402

DEFAULT_CMD = os.environ.get("DWS_EVENT_CMD", "event consume").split()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("WB_DB", "workbench.db"))
    sub = ap.add_subparsers(dest="action", required=True)

    sub.add_parser("init-db")
    p_dump = sub.add_parser("dump-raw")
    p_dump.add_argument("--seconds", type=int, default=30)
    p_dump.add_argument("--out", default="raw-events.ndjson")
    p_dump.add_argument("--cmd", nargs="+", default=DEFAULT_CMD)
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--seconds", type=int, default=60)
    p_sync.add_argument("--cmd", nargs="+", default=DEFAULT_CMD)
    sub.add_parser("stats")
    p_search = sub.add_parser("search")
    p_search.add_argument("--kw", required=True)
    p_search.add_argument("--limit", type=int, default=20)

    args = ap.parse_args()

    if args.action == "init-db":
        store.init_db(args.db)
        print(f"初始化完成：{args.db}")
        return 0

    if args.action == "dump-raw":
        n = 0
        with open(args.out, "w", encoding="utf-8") as fh:
            for ev in dws_client.stream_ndjson(args.cmd, timeout=args.seconds):
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
                n += 1
        print(f"已写入 {n} 条原始事件 -> {args.out}")
        print("下一步：对照真实字段，修正 collector/normalize.py 的 CANDIDATES")
        return 0

    if args.action == "sync":
        store.init_db(args.db)
        conn = store.connect(args.db)
        kept = dup = 0
        try:
            for ev in dws_client.stream_ndjson(args.cmd, timeout=args.seconds):
                rec = normalize.normalize(ev)
                if not rec:
                    continue
                store.upsert_conversation(conn, rec)
                if store.insert_message(conn, rec):
                    kept += 1
                else:
                    dup += 1
            conn.commit()
            store.set_cursor(conn, "dws:event", None)
            conn.commit()
        except Exception as exc:  # 保留游标与错误，便于排查
            store.set_cursor(conn, "dws:event", None, str(exc)[:500])
            conn.commit()
            raise
        print(json.dumps({"inserted": kept, "duplicated": dup}, ensure_ascii=False))
        return 0

    if args.action == "stats":
        conn = store.connect(args.db)
        print(json.dumps(store.stats(conn), ensure_ascii=False, indent=2))
        return 0

    if args.action == "search":
        conn = store.connect(args.db)
        rows = store.search(conn, args.kw, args.limit)
        for r in rows:
            print(f"[{r['sent_at']}] {r['conv_name'] or r['conv_id']} | {r['sender_name']} | {r['text'][:80]}")
        print(f"共 {len(rows)} 条")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
