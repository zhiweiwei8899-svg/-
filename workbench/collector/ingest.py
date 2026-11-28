#!/usr/bin/env python3
"""离线入库与查询：把导出的 NDJSON 归一化后写入 SQLite，或读取已有库。

对应架构文档 M2「存量」：本机导出 JSON → 归一化 → 入库。
不需要 dws，也不需要第三方包（只用标准库 sqlite3 / json）。

用法：
  python3 workbench/collector/ingest.py --action ingest --ndjson raw-events.ndjson
  python3 workbench/collector/ingest.py --action init-db --db workbench/workbench.db
  python3 workbench/collector/ingest.py --action stats   --db workbench/workbench.db
  python3 workbench/collector/ingest.py --action search  --db workbench/workbench.db --keyword 预算 --limit 10

约定：stdout 只输出一行 JSON（宿主据此回报），失败时也是 JSON 且退出码非 0。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import normalize, store  # noqa: E402

DEFAULT_DB = os.environ.get("WB_DB") or str(
    Path(__file__).resolve().parent.parent / "workbench.db"
)


def ingest_ndjson(ndjson_path: str, db_path: str) -> dict:
    """逐行读 NDJSON，归一化后幂等入库；返回计数与入库后的库内统计。"""
    store.init_db(db_path)
    conn = store.connect(db_path)
    inserted = duplicated = skipped = invalid = 0
    try:
        # utf-8-sig：导出的文件可能带 BOM，带不带都能读
        with open(ndjson_path, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    invalid += 1
                    continue
                if not isinstance(raw, dict):
                    invalid += 1
                    continue
                rec = normalize.normalize(raw)
                if not rec:
                    skipped += 1  # 已读/撤回/群变更等非消息事件，v1 不入库
                    continue
                store.upsert_conversation(conn, rec)
                if store.insert_message(conn, rec):
                    inserted += 1
                else:
                    duplicated += 1
        conn.commit()
        summary = store.stats(conn)
    finally:
        conn.close()
    return {
        "db": db_path,
        "ndjson": ndjson_path,
        "inserted": inserted,
        "duplicated": duplicated,
        "skipped_non_message": skipped,
        "invalid_lines": invalid,
        **summary,
    }


def search_messages(db_path: str, keyword: str, limit: int) -> dict:
    conn = store.connect(db_path)
    try:
        rows = [
            {
                "msg_id": r["msg_id"],
                "conv_id": r["conv_id"],
                "conv_name": r["conv_name"] or "",
                "sender_name": r["sender_name"] or "",
                "sent_at": r["sent_at"],
                "text": (r["text"] or "")[:200],
            }
            for r in store.search(conn, keyword, limit)
        ]
    finally:
        conn.close()
    return {"db": db_path, "keyword": keyword, "count": len(rows), "messages": rows}


def _require_db(db_path: str) -> None:
    """读之前先确认库里已经有表：否则 sqlite3.connect 会静默建出一个空文件。"""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"数据库还不存在：{db_path}。先跑 init-db，或用 ingest 导入一份导出。")
    conn = sqlite3.connect(db_path)
    try:
        ready = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchone()
    finally:
        conn.close()
    if not ready:
        raise RuntimeError(f"{db_path} 里还没有 workbench 的表结构。先跑 init-db，或用 ingest 导入一份导出。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="workbench 离线入库与查询")
    ap.add_argument("--action", required=True, choices=["ingest", "init-db", "stats", "search"])
    ap.add_argument("--ndjson", help="事件导出文件，每行一个 JSON 对象（ingest 必填）")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"SQLite 路径，默认 {DEFAULT_DB}")
    ap.add_argument("--keyword", help="检索关键词（search 必填）")
    ap.add_argument("--limit", type=int, default=20, help="检索返回条数上限，默认 20")
    args = ap.parse_args(argv)

    try:
        if args.action == "ingest":
            if not args.ndjson:
                raise ValueError("ingest 需要 --ndjson")
            result = ingest_ndjson(args.ndjson, args.db)
        elif args.action == "init-db":
            store.init_db(args.db)
            result = {"db": args.db, "initialized": True}
        elif args.action == "stats":
            _require_db(args.db)
            conn = store.connect(args.db)
            try:
                result = {"db": args.db, **store.stats(conn)}
            finally:
                conn.close()
        else:
            if not args.keyword:
                raise ValueError("search 需要 --keyword")
            _require_db(args.db)
            limit = max(1, min(int(args.limit), 100))
            result = search_messages(args.db, args.keyword, limit)
    except Exception as exc:  # 归一到一行 JSON，宿主不用去解析 traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
