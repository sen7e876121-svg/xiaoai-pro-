#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qr_login_extract.py — QR 扫码登录提取小米 Token（彻底绕过密码+验证码）
========================================================================

【核心思路】
  完全不走账密登录流程，改用小米的"扫码登录"机制：
  1. 向小米服务器请求一个 QR 码（同电视/路由器的扫码登录入口）
  2. 用你的手机（米家 App / 小爱音箱 App / 系统设置里的小米账号）扫码确认
  3. 长轮询获取登录结果，拿到 passToken + userId
  4. 用 passToken 兑换 xiaomiio 服务的 serviceToken
  5. 调 device_list 获取音箱 DID/Token

  全程不输入密码、不触发验证码、不走浏览器。

【适用平台】macOS / Windows / Linux
【依赖】pip install requests qrcode[pil]

用法：
    python3 qr_login_extract.py
    # 终端会打印一个 QR 码（ASCII 艺术）
    # 如果终端宽度不够，会同时保存为 mi_qr.png
    # 用手机小米账号扫码确认后，脚本自动获取 Token
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

try:
    import qrcode
except ImportError:
    qrcode = None

# ======================================================================
# CONFIG
# ======================================================================
# QR 码登录的接口（小米官方，用于电视、路由器等无键盘设备的登录）
QR_LOGIN_URL = "https://account.xiaomi.com/longPolling/loginUrl"

# 检查 QR 扫码状态的接口
# 注意：实际使用时需从 loginUrl 响应中提取 polling URL
QR_POLL_BASE = "https://account.xiaomi.com/longPolling/loginUrl"

# passToken 兑换 serviceToken 的接口
SERVICE_LOGIN_URL = "https://account.xiaomi.com/pass/serviceLogin"

# MiIO 设备列表
MIIO_DEVICE_LIST_URL = "https://api.io.mi.com/app/home/device_list"

# 音箱过滤
SPEAKER_KEYWORDS = ("speaker", "lx")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# ======================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("qr_login")


def display_qr_code(url: str) -> None:
    """在终端打印 QR 码，并保存为图片文件"""
    if qrcode:
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        # 终端 ASCII 显示
        qr.print_ascii(invert=True)
        # 同时保存为图片（终端太小看不清时用）
        img = qr.make_image(fill_color="black", back_color="white")
        img.save("mi_qr.png")
        log.info("QR 码已保存为 mi_qr.png（用图片查看器打开也行）")
    else:
        print(f"\n请手动在浏览器打开以下链接生成 QR 码，或用在线工具：\n{url}\n")
        print("提示：安装 qrcode 库可直接在终端显示：pip install qrcode[pil]")


def request_qr_login() -> dict:
    """
    请求小米的 QR 扫码登录入口。

    返回包含 QR 码 URL 和 polling 信息的 dict。
    """
    headers = {
        "User-Agent": (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            "0000000000 APP/xiaomi.smarthome APPV/62830"
        ),
    }
    # 请求 QR 登录 URL
    # sid=xiaomiio 让我们直接拿到 xiaomiio 服务的授权
    params = {
        "sid": "xiaomiio",
        "_json": "true",
    }

    resp = requests.get(QR_LOGIN_URL, params=params, headers=headers, timeout=15)
    text = resp.text.replace("&&&START&&&", "").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.error("QR 登录接口返回异常: %s", resp.text[:200])
        sys.exit(1)

    return data


def poll_qr_status(login_url: str, timeout_seconds: int = 300) -> dict:
    """
    长轮询等待用户扫码确认。

    小米的 QR 登录是长轮询机制：
    - 客户端每隔几秒请求一次状态
    - 未扫码：返回等待状态
    - 已扫码未确认：返回等待确认
    - 已确认：返回 passToken + userId 等信息
    """
    headers = {
        "User-Agent": (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            "0000000000 APP/xiaomi.smarthome APPV/62830"
        ),
    }

    start = time.time()
    attempt = 0

    while time.time() - start < timeout_seconds:
        attempt += 1
        try:
            resp = requests.get(login_url, headers=headers, timeout=30)
            text = resp.text.replace("&&&START&&&", "").strip()
            data = json.loads(text)

            # 检查登录状态
            if data.get("code") == 0 or "passToken" in str(data):
                log.info("扫码登录成功！")
                return data
            elif "nonce" in data or data.get("code") == 2:
                # 还在等待扫码
                if attempt % 5 == 0:
                    elapsed = int(time.time() - start)
                    log.info("等待扫码中 ... (%ds/%ds)", elapsed, timeout_seconds)
            else:
                log.debug("poll 响应: %s", text[:100])

        except requests.Timeout:
            # 长轮询超时是正常的，继续下一轮
            pass
        except Exception as e:
            log.warning("poll 请求异常: %s", e)

        time.sleep(3)

    log.error("等待扫码超时（%d 秒），请重新运行脚本。", timeout_seconds)
    sys.exit(1)


def exchange_service_token(pass_token: str, user_id: str, sid: str = "xiaomiio") -> str:
    """用 passToken 兑换指定 sid 的 serviceToken"""
    headers = {
        "User-Agent": (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            f"{user_id} APP/xiaomi.smarthome APPV/62830"
        ),
        "Cookie": f"passToken={pass_token}; userId={user_id}",
    }
    params = {"sid": sid, "_json": "true"}

    resp = requests.get(SERVICE_LOGIN_URL, params=params, headers=headers, timeout=15)
    text = resp.text.replace("&&&START&&&", "").strip()
    data = json.loads(text)

    if "location" not in data:
        raise RuntimeError(f"serviceLogin 失败: {data}")

    # 跟随 location 拿 serviceToken
    location = data["location"]
    resp2 = requests.get(location, headers=headers, allow_redirects=False, timeout=15)

    for cookie in resp2.cookies:
        if "serviceToken" in cookie.name:
            return cookie.value

    raise RuntimeError("未从 location 重定向中获取到 serviceToken")


def fetch_device_list(service_token: str, user_id: str) -> list[dict]:
    """查询 MiIO 设备列表"""
    headers = {
        "Cookie": f"serviceToken={service_token}; userId={user_id}",
        "User-Agent": (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            f"{user_id} APP/xiaomi.smarthome APPV/62830"
        ),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"getVirtualModel": "false", "getHuamiDevices": "0"}

    resp = requests.post(MIIO_DEVICE_LIST_URL, headers=headers, data=data, timeout=15)
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"device_list 返回错误: {result}")

    return result.get("result", {}).get("list", [])


def print_results(devices: list[dict]) -> None:
    """打印设备列表"""
    speakers = [d for d in devices if any(
        kw in f"{d.get('model', '')} {d.get('name', '')}".lower()
        for kw in SPEAKER_KEYWORDS
    )]

    print()
    print("=" * 100)
    print(f"共获取到 {len(devices)} 台设备，其中音箱 {len(speakers)} 台")
    print("=" * 100)

    for dev in speakers:
        print(
            f"\n  [SPEAKER] {dev.get('name', '?')}\n"
            f"    Hardware (model): {dev.get('model', '?')}\n"
            f"    MI_DID:           {dev.get('did', '?')}\n"
            f"    Token:            {dev.get('token', '?')}\n"
            f"    Local IP:         {dev.get('localip', '?')}\n"
            f"    MAC:              {dev.get('mac', '?')}"
        )

    if speakers:
        print("\n" + "-" * 100)
        print("JSON（直接粘贴到 config.json）：")
        export = [
            {"hardware": s.get("model"), "mi_did": s.get("did"), "mi_token": s.get("token")}
            for s in speakers
        ]
        print(json.dumps(export, ensure_ascii=False, indent=2))

    # 保存全量
    Path("mi_devices_full.json").write_text(json.dumps(devices, ensure_ascii=False, indent=2))


def main() -> None:
    print(
        "\n"
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║  小米 Token 提取器（QR 扫码模式）                                ║\n"
        "║                                                                  ║\n"
        "║  全程不输入密码、不触发验证码。                                    ║\n"
        "║  只需用手机扫描下方 QR 码并在米家 App 中确认即可。                ║\n"
        "╚══════════════════════════════════════════════════════════════════╝\n"
    )

    # Step 1: 获取 QR 登录信息
    log.info("正在请求 QR 扫码登录入口 ...")
    qr_data = request_qr_login()

    # 从响应中提取 QR 码 URL 和 polling URL
    qr_url = qr_data.get("loginUrl") or qr_data.get("lp") or qr_data.get("qr")
    if not qr_url:
        log.error("无法从响应中提取 QR 码 URL: %s", qr_data)
        log.info("小米可能更改了 QR 登录接口，请改用方案 1（Selenium 浏览器模式）")
        sys.exit(1)

    # Step 2: 显示 QR 码
    print("\n请用手机扫描以下 QR 码（米家 App / 小爱音箱 App / 系统设置-小米账号）：\n")
    display_qr_code(qr_url)
    print(f"\n或手动访问: {qr_url}\n")

    # Step 3: 轮询等待扫码结果
    log.info("等待扫码确认（最多 5 分钟）...")
    poll_url = qr_data.get("lp") or qr_url
    result = poll_qr_status(poll_url)

    # Step 4: 提取 passToken 和 userId
    pass_token = result.get("passToken")
    user_id = str(result.get("userId", ""))

    if not pass_token or not user_id:
        log.error("扫码响应中缺少 passToken/userId: %s", result)
        sys.exit(1)

    log.info("获取到 userId=%s, passToken=%s...", user_id, pass_token[:10])

    # Step 5: 用 passToken 兑换 xiaomiio serviceToken
    log.info("正在用 passToken 兑换 xiaomiio serviceToken ...")
    try:
        service_token = exchange_service_token(pass_token, user_id, "xiaomiio")
        log.info("serviceToken 兑换成功（len=%d）", len(service_token))
    except Exception as e:
        log.error("兑换 serviceToken 失败: %s", e)
        log.info("尝试直接用 passToken 列出设备 ...")
        service_token = pass_token  # 兜底尝试

    # Step 6: 拉取设备列表
    log.info("正在拉取设备列表 ...")
    try:
        devices = fetch_device_list(service_token, user_id)
    except Exception as e:
        log.error("获取设备列表失败: %s", e)
        sys.exit(1)

    print_results(devices)

    # Step 7: 保存 .mi.token 供 xiaogpt 复用
    mi_token_data = {
        "userId": user_id,
        "passToken": pass_token,
        "serviceToken": service_token,
    }
    mi_token_path = Path.home() / ".mi.token"
    mi_token_path.write_text(json.dumps(mi_token_data, indent=2))
    log.info("认证态已保存到 %s", mi_token_path)
    print(f"\n✅ 完成！认证信息已保存到 {mi_token_path}")
    print("   后续 xiaogpt 容器挂载 .mi.token 即可免登录启动。")


if __name__ == "__main__":
    main()
