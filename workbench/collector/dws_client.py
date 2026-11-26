"""dws CLI 的薄封装：只负责调命令、收 JSON/NDJSON、把错误抛清楚。

注意：dws 尚未 GA，子命令与输出字段可能变化。本模块把「命令」与「解析」分离，
命令可通过环境变量 DWS_BIN / DWS_EVENT_CMD 覆盖，解析在 normalize.py 里做防御式映射。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Iterator

DWS_BIN = os.environ.get("DWS_BIN", "dws")


class DwsError(RuntimeError):
    pass


def ensure_available() -> str:
    path = shutil.which(DWS_BIN)
    if not path:
        raise DwsError(
            f"找不到 dws 可执行文件（DWS_BIN={DWS_BIN}）。"
            "请先安装并完成 dws auth login。"
        )
    return path


def run_json(args: list[str], timeout: int = 60) -> dict:
    """执行一次返回单个 JSON 对象的命令，例如 `dws chat group list`。"""
    out = _run(args, timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DwsError(f"输出不是合法 JSON：{exc}\n原始输出前 500 字：{out[:500]}") from exc


def stream_ndjson(args: list[str], timeout: int = 60) -> Iterator[dict]:
    """执行一次持续输出 NDJSON 的命令（如 `dws event consume`），逐行产出。

    timeout 是本函数等待单行的最长秒数；到达后结束迭代，由调用方决定是否重连。
    """
    proc = subprocess.Popen(
        [DWS_BIN, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env={**os.environ, "DWS_DISABLE_KEYCHAIN": os.environ.get("DWS_DISABLE_KEYCHAIN", "1")},
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # 非 JSON 行（如进度提示）直接跳过，保留在 stderr 侧排查
                continue
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _run(args: list[str], timeout: int) -> str:
    ensure_available()
    proc = subprocess.run(
        [DWS_BIN, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "DWS_DISABLE_KEYCHAIN": os.environ.get("DWS_DISABLE_KEYCHAIN", "1")},
    )
    if proc.returncode != 0:
        raise DwsError(
            f"dws 返回 {proc.returncode}：{' '.join(args)}\n"
            f"stderr: {proc.stderr.strip()[:800]}"
        )
    return proc.stdout
