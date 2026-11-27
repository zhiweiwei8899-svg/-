#!/usr/bin/env python3
"""dws 自检：只输出命令面与字段结构，不泄露消息内容和凭据。

用法（在你已授权 dws 的机器上）：
    python3 workbench/collector/selftest.py > dws-report.txt

然后把 dws-report.txt 的内容发给我。脚本会做三件事：
1) 打印 dws 版本、认证状态（只保留组织名与数量）、profile 数量
2) 打印各子命令的 help 摘要（用于确认我这边的命令名是否写对）
3) 采样最多 3 条事件，只输出字段名与类型，字符串值统一截断为前 12 字并打码

注意：report 里可能出现群名/人名（前 12 字）。如仍敏感，可加 --no-names，
此时所有字符串只显示长度。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import threading

SENSITIVE_KEY = re.compile(r"(token|secret|cookie|password|credential|auth)", re.I)


def run(args: list[str], timeout: int = 45) -> tuple[int, str]:
    try:
        p = subprocess.run(["dws", *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    except FileNotFoundError:
        return 127, "dws 未安装或不在 PATH"
    except subprocess.TimeoutExpired:
        return 124, f"超时（{timeout}s）"


def mask(obj, no_names: bool, depth: int = 0):
    """递归输出结构：只保留字段名与类型，字符串截断。"""
    if depth > 6:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if SENSITIVE_KEY.search(k):
                out[k] = "<redacted>"
            else:
                out[k] = mask(v, no_names, depth + 1)
        return out
    if isinstance(obj, list):
        return [mask(obj[0], no_names, depth + 1)] + ([f"...共{len(obj)}项"] if len(obj) > 1 else [])
    if isinstance(obj, str):
        if no_names:
            return f"<str:{len(obj)}>"
        return (obj[:12] + "…") if len(obj) > 12 else obj
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-names", action="store_true", help="连字符串内容也不显示")
    ap.add_argument("--seconds", type=int, default=20, help="事件采样时长")
    args = ap.parse_args()

    print("=" * 60)
    print("dws 自检报告")
    print("=" * 60)

    if not shutil.which("dws"):
        print("dws: 未找到，请确认已安装并在 PATH 中")
        return 1

    code, out = run(["--version"])
    print(f"\n## 版本\n{out.strip()[:300]}")

    print("\n## 认证状态")
    code, out = run(["auth", "status", "-f", "json"])
    try:
        data = json.loads(out)
        print(json.dumps(mask(data, args.no_names), ensure_ascii=False, indent=2)[:2000])
    except Exception:
        print(f"(非 JSON 输出，exit={code})\n{out.strip()[:800]}")

    print("\n## 子命令面（只列命令名，不列参数值）")
    for grp in ("chat", "event", "wiki", "drive", "doc", "oa", "todo", "aitable"):
        code, out = run([grp, "--help"])
        names = sorted(set(re.findall(r"^\s{2,}([a-z][a-z0-9-]+)\s{2,}", out, re.M)))
        status = "OK" if code == 0 else f"exit={code}"
        print(f"- dws {grp}: {status} | {', '.join(names[:14]) if names else '(未解析到子命令)'}")

    print(f"\n## 事件字段结构（采样 {args.seconds}s，最多 3 条，仅结构与类型）")
    proc = subprocess.Popen(
        ["dws", "event", "consume"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        env={**__import__("os").environ, "DWS_DISABLE_KEYCHAIN": "1"},
    )
    got = 0
    killer = threading.Timer(args.seconds, proc.terminate)
    killer.start()
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            got += 1
            print(f"\n### 事件 {got}")
            print(json.dumps(mask(ev, args.no_names), ensure_ascii=False, indent=2)[:2500])
            if got >= 3:
                break
    finally:
        killer.cancel()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    if got == 0:
        err = (proc.stderr.read() if proc.stderr else "")[:600]
        print("(未采到事件。可能原因：当前授权范围无消息事件、需先注册事件、或命令名变化)")
        print(f"stderr: {err}")

    print("\n## 完成。把以上全部内容发给我即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
