#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_mi_info.py
==============

获取小米账号下所有设备的关键信息（Hardware / DID / Token），并过滤出
小爱音箱类设备（标识含 'speaker' 或 'lx'），用于 python-miio / node-mihome /
Home Assistant / xiaogpt 等第三方集成。

适用平台：macOS (Apple Silicon / Intel) / Windows 10/11 / Linux

依赖：
    pip install -r requirements.txt

使用：
    1. 替换下方 CONFIG 区的 <YOUR_USERNAME> / <YOUR_PASSWORD>（或改用环境变量）
    2. python get_mi_info.py
    3. 输出中带 [SPEAKER] 标记的行即为小爱音箱，记下其 DID 和 Token
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import aiohttp
from miservice import MiAccount, MiIOService

# ======================================================================
# === CONFIG 区：请替换下方占位符 =======================================
# ======================================================================
# ⚠️ 两种方式任选其一：
#   方式 A（推荐）：设置环境变量 MI_USER / MI_PASS，避免明文入库
#       macOS/Linux:   export MI_USER="你的账号"; export MI_PASS="你的密码"
#       Windows PS:    $env:MI_USER="你的账号"; $env:MI_PASS="你的密码"
#   方式 B：直接修改下方占位符（仅本机调试用，勿提交到 Git）

# <YOUR_USERNAME> → 小米账号（手机号 / 邮箱 / 小米 ID）
MI_USER: str = os.getenv("MI_USER", "<YOUR_USERNAME>")

# <YOUR_PASSWORD> → 小米账号密码
MI_PASS: str = os.getenv("MI_PASS", "<YOUR_PASSWORD>")

# Token 缓存文件路径（首次登录后 miservice 会把登录态缓存到此文件，
# 下次运行免去重复登录，避免触发小米风控）
# <TOKEN_CACHE_PATH> → 默认放在用户主目录，跨平台通用
MI_TOKEN_CACHE: Path = Path(
    os.getenv("MI_TOKEN_CACHE", str(Path.home() / ".mi.token"))
)

# 音箱过滤关键字（不分大小写）
# 'speaker' 覆盖大部分小爱音箱型号（如 xiaomi.wifispeaker.*）
# 'lx'      覆盖 Pro / Play / Art 等型号（model 中常见 lx01/lx04/lx05/lx06/lx5a 等）
SPEAKER_KEYWORDS: tuple[str, ...] = ("speaker", "lx")

# 网络请求超时（秒）
HTTP_TIMEOUT: int = 30

# 日志级别：DEBUG / INFO / WARNING / ERROR
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
# ======================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("get_mi_info")


def _looks_like_speaker(device: dict[str, Any]) -> bool:
    """
    判定一个设备是否为小爱音箱。

    规则：设备的 model（如 'xiaomi.wifispeaker.lx04'）或 name 中
    出现任意关键字（'speaker' / 'lx'）即视为音箱。
    """
    haystack = " ".join(
        str(device.get(k, "")) for k in ("model", "name", "did")
    ).lower()
    return any(kw in haystack for kw in SPEAKER_KEYWORDS)


def _format_device_row(device: dict[str, Any], is_speaker: bool) -> str:
    """格式化输出一行设备信息，音箱加 [SPEAKER] 醒目标记。"""
    tag = "[SPEAKER]" if is_speaker else "         "
    name = str(device.get("name", "")).ljust(20)[:20]
    model = str(device.get("model", "")).ljust(28)[:28]
    did = str(device.get("did", "")).ljust(20)[:20]
    token = str(device.get("token", ""))
    localip = str(device.get("localip", "")).ljust(15)[:15]
    return f"{tag}  {name}  {model}  DID={did}  IP={localip}  TOKEN={token}"


async def fetch_devices() -> list[dict[str, Any]]:
    """
    登录小米云并拉取设备列表。

    内部会自动做：
      - 首次调用：走账号密码登录，session 写入 MI_TOKEN_CACHE
      - 后续调用：复用缓存的 serviceToken，避免触发风控
      - 登录失败：miservice 自身会抛异常，我们向上冒泡并打印友好提示
    """
    # 单独的 timeout，防止网络抖动导致永久挂起
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        account = MiAccount(
            session,
            MI_USER,
            MI_PASS,
            str(MI_TOKEN_CACHE),
        )
        service = MiIOService(account)

        log.info("正在向小米云拉取设备列表 ...")
        # device_list() 返回 list[dict]，每个 dict 至少包含：
        #   name, did, token, model, localip, mac, isOnline, ...
        devices = await service.device_list()
        return devices or []


def print_report(devices: list[dict[str, Any]]) -> None:
    """打印人类可读的设备清单，并单独再给一份音箱 JSON 便于复制粘贴。"""
    if not devices:
        log.warning("未获取到任何设备。请确认账号下已绑定小米设备、且账号密码正确。")
        return

    speakers: list[dict[str, Any]] = []

    print()
    print("=" * 120)
    print(f"账号 {MI_USER} 下共发现 {len(devices)} 台设备：")
    print("-" * 120)
    for dev in devices:
        is_speaker = _looks_like_speaker(dev)
        if is_speaker:
            speakers.append(dev)
        print(_format_device_row(dev, is_speaker))
    print("=" * 120)

    # === 音箱单独输出 JSON，方便直接粘贴到 xiaogpt / HA 配置 ===
    if speakers:
        print()
        print(f"命中 {len(speakers)} 台小爱音箱（按 'speaker' / 'lx' 关键字过滤）：")
        print("-" * 120)
        concise = [
            {
                "name": s.get("name"),
                "hardware": s.get("model"),  # Hardware 型号即 model 字段
                "mi_did": s.get("did"),
                "token": s.get("token"),
                "localip": s.get("localip"),
                "mac": s.get("mac"),
            }
            for s in speakers
        ]
        print(json.dumps(concise, ensure_ascii=False, indent=2))
        print("-" * 120)
        print("提示：DID 和 TOKEN 即为 xiaogpt / python-miio / HA 所需的关键凭据。")
    else:
        log.warning("未过滤到小爱音箱（关键字：%s）。", ", ".join(SPEAKER_KEYWORDS))


async def main_async() -> int:
    # 启动前校验占位符是否已替换
    if MI_USER.startswith("<") or MI_PASS.startswith("<"):
        log.error(
            "检测到 MI_USER / MI_PASS 仍为占位符，请先替换或设置环境变量 "
            "MI_USER / MI_PASS 再运行。"
        )
        return 2

    try:
        devices = await fetch_devices()
    except aiohttp.ClientError as e:
        log.error("网络错误：%s", e)
        return 10
    except asyncio.TimeoutError:
        log.error("请求超时（%d 秒），请检查网络或代理。", HTTP_TIMEOUT)
        return 11
    except Exception as e:  # noqa: BLE001
        # miservice 内部登录失败会抛普通 Exception，这里兜底并给出可操作提示
        log.exception("登录或拉取设备失败：%s", e)
        log.error(
            "排查建议：\n"
            "  1. 确认账号密码正确（首次运行需真实登录）\n"
            "  2. 若开启了小米账号二次验证，请临时关闭后再运行\n"
            "  3. 删除 Token 缓存文件后重试：%s",
            MI_TOKEN_CACHE,
        )
        return 1

    print_report(devices)
    return 0


def main() -> None:
    # Windows 下 aiohttp 需显式使用 SelectorEventLoop 以兼容部分环境
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
