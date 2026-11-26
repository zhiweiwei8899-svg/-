#!/usr/bin/env python3
"""最小可用：钉钉群机器人（Stream 模式）+ 千问回答。

特性：
- 无需公网 IP / 域名（Stream 长连接）
- 按 msgId 去重，防止钉钉重推导致重复回答
- 千问走 DashScope OpenAI 兼容接口，便于换模型
- 异常不崩：调用失败时回一句兜底文案，并打印日志

运行前准备（.env）：
  DINGTALK_APP_KEY / DINGTALK_APP_SECRET
  DASHSCOPE_API_KEY
  QWEN_MODEL（默认 qwen-plus）
"""
from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict

import dingtalk_stream
import requests
from dingtalk_stream import AckMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

APP_KEY = os.environ["DINGTALK_APP_KEY"]
APP_SECRET = os.environ["DINGTALK_APP_SECRET"]
DASHSCOPE_KEY = os.environ["DASHSCOPE_API_KEY"]
MODEL = os.environ.get("QWEN_MODEL", "qwen-plus")
ENDPOINT = os.environ.get(
    "QWEN_ENDPOINT",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
SYSTEM_PROMPT = os.environ.get(
    "BOT_SYSTEM_PROMPT",
    "你是钉钉群里的助手。回答简洁、用中文；不确定就直说不确定，不要编造。",
)

# 去重：钉钉可能重投同一消息，保留最近 2000 个 msgId
_seen: OrderedDict[str, float] = OrderedDict()


def is_duplicate(msg_id: str) -> bool:
    if not msg_id:
        return False
    if msg_id in _seen:
        return True
    _seen[msg_id] = time.time()
    while len(_seen) > 2000:
        _seen.popitem(last=False)
    return False


def ask_qwen(question: str, retries: int = 2) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {DASHSCOPE_KEY}", "Content-Type": "application/json"}
    last_err = None
    for i in range(retries + 1):
        try:
            r = requests.post(ENDPOINT, json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                return data["choices"][0]["message"]["content"].strip()
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as exc:
            last_err = str(exc)
        log.warning("千问调用失败（第 %d 次）：%s", i + 1, last_err)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"千问调用失败：{last_err}")


class Handler(dingtalk_stream.ChatbotHandler):
    async def process(self, callback) -> tuple[int, str]:
        try:
            msg = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            msg_id = getattr(msg, "message_id", "") or ""
            if is_duplicate(msg_id):
                log.info("重复消息，跳过：%s", msg_id)
                return AckMessage.STATUS_OK, "OK"

            text = (msg.text.content or "").strip() if msg.text else ""
            if not text:
                self.reply_text("目前只支持文本提问。", msg)
                return AckMessage.STATUS_OK, "OK"

            log.info("收到提问 conv=%s sender=%s len=%d", msg.conversation_id, msg.sender_nick, len(text))
            try:
                answer = ask_qwen(text)
            except Exception:
                answer = "抱歉，模型暂时不可用，请稍后再试。"
            self.reply_text(answer[:4000], msg)
            return AckMessage.STATUS_OK, "OK"
        except Exception:
            log.exception("处理消息异常")
            # 仍然 ACK，避免钉钉无限重推
            return AckMessage.STATUS_OK, "OK"


def main() -> None:
    credential = dingtalk_stream.Credential(APP_KEY, APP_SECRET)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC, Handler()
    )
    log.info("机器人已启动，等待消息（model=%s）", MODEL)
    client.start_forever()


if __name__ == "__main__":
    main()
