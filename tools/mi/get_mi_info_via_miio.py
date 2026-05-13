#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_mi_info_via_miio.py — Mina 风控后的备用设备提取脚本
==========================================================

【问题背景】
  Docker 容器无 token 持久化 → 频繁登录触发 Mina 服务风控 →
  api2.mina.mi.com/admin/v2/device_list 返回 "Login failed"

【本脚本策略】
  绕开 Mina（sid=micoapi），改走 MiIO（sid=xiaomiio）的 device_list 接口
  （api.io.mi.com），两个服务风控独立，大概率后者仍可用。

适用平台：macOS (Apple Silicon / Intel) / Windows 10/11 / Linux
依赖：pip install miservice_fork aiohttp

用法：
    # === macOS / Linux ===
    export MI_USER="<YOUR_MI_ACCOUNT>"    # ⚠️ 替换为你的小米账号
    export MI_PASS="<YOUR_MI_PASSWORD>"   # ⚠️ 替换为你的小米密码
    python3 get_mi_info_via_miio.py

    # === Windows 10/11 - PowerShell 7+ ===
    $env:MI_USER="<YOUR_MI_ACCOUNT>"
    $env:MI_PASS="<YOUR_MI_PASSWORD>"
    python .\\get_mi_info_via_miio.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import aiohttp
from miservice import MiAccount, MiIOService

# ======================================================================
# === CONFIG 区 =========================================================
# ======================================================================
# ⚠️ 请替换 <YOUR_MI_ACCOUNT> / <YOUR_MI_PASSWORD> 为你的真实小米账号密码
#   或通过环境变量 MI_USER / MI_PASS 传入（推荐后者，密码不落盘）

MI_USER: str = os.getenv("MI_USER", "<YOUR_MI_ACCOUNT>")
MI_PASS: str = os.getenv("MI_PASS", "<YOUR_MI_PASSWORD>")

# Token 缓存文件 — 登录态持久化，避免重复登录触发风控
# 默认放用户主目录，路径跨平台通用
MI_TOKEN_CACHE: Path = Path(
    os.getenv("MI_TOKEN_CACHE", str(Path.home() / ".mi.token"))
)

# 音箱过滤关键字（不分大小写）
SPEAKER_KEYWORDS: tuple[str, ...] = ("speaker", "lx")

# 网络超时（秒）
HTTP_TIMEOUT: int = 30

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
# ======================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("get_mi_info_miio")


def is_speaker(device: dict) -> bool:
    """判定设备是否为小爱音箱（model 或 name 含 speaker / lx）"""
    haystack = f"{device.get('model', '')} {device.get('name', '')}".lower()
    return any(kw in haystack for kw in SPEAKER_KEYWORDS)


async def main_async() -> int:
    # 检测占位符
    if MI_USER.startswith("<") or MI_PASS.startswith("<"):
        log.error(
            "MI_USER / MI_PASS 仍为占位符！请先设置环境变量或直接修改脚本顶部 CONFIG 区。"
        )
        return 2

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        account = MiAccount(session, MI_USER, MI_PASS, str(MI_TOKEN_CACHE))

        # ==============================================================
        # 核心区别：MiIOService 走 xiaomiio sid，而非 micoapi sid
        # 两者共享同一台设备库，但风控策略独立
        # 如果 Mina 被封了（device_list "Login failed"），试这条路
        # ==============================================================
        miio = MiIOService(account)

        log.info("正在通过 MiIO 服务（api.io.mi.com / sid=xiaomiio）拉取设备 ...")
        log.info("此接口与 Mina（api2.mina.mi.com）风控独立。")

        try:
            devices = await miio.device_list()
        except Exception as e:
            log.exception("MiIO device_list 也失败了：%s", e)
            log.error(
                "\n=== 排查建议 ===\n"
                "  1. 删除 token 缓存重试：rm %s\n"
                "  2. 换一个完全干净的网络（确保 IP 之前没被用来发过请求）\n"
                "  3. 如果账号在 12h 内被连续轰炸过，等 24-48h 后重试\n"
                "  4. 终极方案：见 manual_token_extract.md（手动抓包/米家日志提取）",
                MI_TOKEN_CACHE,
            )
            return 1

    if not devices:
        log.warning("设备列表为空。请确认账号正确、设备已在米家绑定。")
        return 0

    speakers = [d for d in devices if is_speaker(d)]

    print()
    print("=" * 100)
    print(f"通过 MiIO 获取到 {len(devices)} 台设备，其中音箱 {len(speakers)} 台")
    print("=" * 100)

    for dev in speakers:
        print(
            f"\n  [SPEAKER] {dev.get('name', '?')}\n"
            f"    Hardware (model): {dev.get('model', '?')}\n"
            f"    MI_DID:           {dev.get('did', '?')}\n"
            f"    Token:            {dev.get('token', '?')}\n"
            f"    Local IP:         {dev.get('localip', '?')}\n"
            f"    MAC:              {dev.get('mac', '?')}\n"
            f"    Online:           {dev.get('isOnline', '?')}"
        )

    if speakers:
        print("\n" + "-" * 100)
        print("JSON（直接粘贴到 xiaogpt-server/config.json 对应字段）：")
        print("-" * 100)
        export = [
            {
                "hardware": s.get("model"),
                "mi_did": s.get("did"),
                "mi_token": s.get("token"),
                "name": s.get("name"),
                "localip": s.get("localip"),
            }
            for s in speakers
        ]
        print(json.dumps(export, ensure_ascii=False, indent=2))
        print()
        print("👆 把 mi_did 和 mi_token 填到 config.json，再 docker compose restart")
    else:
        log.warning("未找到音箱设备（关键字：%s）。", ", ".join(SPEAKER_KEYWORDS))
        log.info("如果你确认有 lx06，可能设备在另一个小米账号下，或 model 命名变动。")

    return 0


def main() -> None:
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
