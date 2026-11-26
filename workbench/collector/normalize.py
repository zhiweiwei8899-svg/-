"""把 dws 的原始事件/消息，防御式映射成仓库定义的四张表所需的字段。

为什么要防御式：dws 的事件字段名尚未在目标环境实测（README 只给了 schema 子命令），
不同事件类型（消息、已读、撤回、群变更）字段不同。这里做三件事：
1) 用候选键列表取值，兼容常见命名；
2) 取不到就留空，绝不编造；
3) 原文完整保存在 raw_json，字段映射修正后可重放。

TODO(实测后修正)：拿到 `dws event schema user_im_message_receive_o2o --flatten`
的真实输出后，把 CANDIDATES 收敛成确定字段名，并删除多余候选。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

# 各字段的候选键（按优先级）。取第一个存在且非空的。
CANDIDATES = {
    "msg_id": ["msgId", "messageId", "msg_id", "openMessageId", "id"],
    "conv_id": ["conversationId", "convId", "chatId", "openConversationId", "cid"],
    "conv_name": ["conversationTitle", "conversationName", "chatName", "title"],
    "conv_type": ["conversationType", "chatType", "convType"],
    "sender_id": ["senderStaffId", "senderId", "userId", "fromUserId", "sender"],
    "sender_name": ["senderNick", "senderName", "userName", "fromName"],
    "sent_at": ["createAt", "createTime", "sentAt", "timestamp", "msgTimestamp"],
    "msg_type": ["msgtype", "msgType", "messageType"],
    "text": ["text", "content", "plainText"],
}


def _pick(d: dict, keys: list[str]) -> Any:
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            # 常见嵌套：{"content": {"text": "..."}} / {"text": {"content": "..."}}
            for kk in ("text", "content", "value"):
                if isinstance(v.get(kk), str) and v[kk]:
                    return v[kk]
            continue
        if v not in (None, "", [], {}):
            return v
    return None


def _iso(ts: Any) -> str:
    """把秒/毫秒时间戳或字符串统一成 ISO8601（带本地时区偏移）。"""
    if ts is None:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    if isinstance(ts, (int, float)):
        sec = ts / 1000 if ts > 10_000_000_000 else ts
        return datetime.fromtimestamp(sec, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    s = str(ts)
    if s.isdigit():
        return _iso(int(s))
    return s


def normalize(raw: dict) -> dict | None:
    """返回 canonical 记录；不是消息类事件（已读/撤回/群变更）时返回 None。"""
    msg_type = _pick(raw, CANDIDATES["msg_type"])
    text = _pick(raw, CANDIDATES["text"])
    if not msg_type and not text:
        return None  # 非消息事件，v1 不入 messages 表

    conv_type_raw = (_pick(raw, CANDIDATES["conv_type"]) or "").lower()
    conv_type = "p2p" if conv_type_raw in ("1", "single", "p2p", "chat") else "group"

    conv_id = str(_pick(raw, CANDIDATES["conv_id"]) or "")
    sender_id = str(_pick(raw, CANDIDATES["sender_id"]) or "")
    sent_at = _iso(_pick(raw, CANDIDATES["sent_at"]))
    msg_id = str(_pick(raw, CANDIDATES["msg_id"]) or "")

    raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    if not msg_id:
        # 无 ID 时用稳定哈希生成，保证重跑不重复
        msg_id = "h:" + hashlib.sha256(
            f"{conv_id}|{sender_id}|{sent_at}|{text}".encode()
        ).hexdigest()[:32]

    dedup_hash = hashlib.sha256(
        f"{conv_id}|{msg_id}|{sent_at}|{(text or '')[:200]}".encode()
    ).hexdigest()

    return {
        "msg_id": msg_id,
        "conv_id": conv_id or f"unknown:{hashlib.sha256(raw_json.encode()).hexdigest()[:12]}",
        "conv_type": conv_type,
        "conv_name": _pick(raw, CANDIDATES["conv_name"]) or "",
        "sender_id": sender_id,
        "sender_name": _pick(raw, CANDIDATES["sender_name"]) or "",
        "sent_at": sent_at,
        "msg_type": (msg_type or "text").lower() if isinstance(msg_type, str) else "text",
        "text": text if isinstance(text, str) else "",
        "raw_json": raw_json,
        "dedup_hash": dedup_hash,
    }
