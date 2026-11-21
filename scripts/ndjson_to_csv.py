#!/usr/bin/env python3
"""canonical NDJSON -> CSV（无第三方依赖）

用途：把归一化后的消息/附件记录导出为 CSV，供 dws aitable 导入或 Excel 查看。
数据契约见 docs/architecture.md 的「统一数据模型」。

用法：
  python3 scripts/ndjson_to_csv.py messages.ndjson > messages.csv
  python3 scripts/ndjson_to_csv.py attachments.ndjson --type attachments > attachments.csv

输入：每行一个 JSON 对象的 NDJSON 文件（'-' 表示 stdin）。
输出：UTF-8 BOM 的 CSV（Excel 直接双击打开不乱码）。
"""
import argparse
import csv
import io
import json
import sys

SCHEMAS = {
    "messages": [
        "msg_id", "conv_id", "conv_type", "conv_name", "sender_id",
        "sender_name", "sent_at", "msg_type", "text",
    ],
    "attachments": [
        "att_id", "msg_id", "file_name", "file_type", "size_bytes",
        "local_path", "parsed_path", "parse_status",
    ],
    "kb_nodes": [
        "node_id", "space_id", "parent_id", "title", "kind",
        "synced_at", "rag_doc_id",
    ],
}


def rows(path):
    stream = sys.stdin if path == "-" else open(path, encoding="utf-8")
    with stream as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno} 不是合法 JSON：{exc}")


def main():
    ap = argparse.ArgumentParser(description="canonical NDJSON -> CSV")
    ap.add_argument("input", help="NDJSON 文件路径，'-' 表示 stdin")
    ap.add_argument("--type", default="messages", choices=sorted(SCHEMAS),
                    help="记录类型，决定列顺序")
    args = ap.parse_args()

    cols = SCHEMAS[args.type]
    stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8-sig", newline="")
    out = csv.writer(stream, lineterminator="\n")
    out.writerow(cols)
    n = 0
    for rec in rows(args.input):
        out.writerow([rec.get(c, "") for c in cols])
        n += 1
    stream.flush()
    print(f"# 已写出 {n} 行 -> {args.type}.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
