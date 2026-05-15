#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
browser_token_extract.py — 用 Selenium 真实浏览器绕过滑块验证，提取小米 Token
===================================================================================

【核心思路】
  不做任何"伪装"——直接用真实浏览器（Chromium）走小米登录流程。
  你手动完成滑块/验证码，脚本从浏览器的 Cookie 中提取出已认证的
  passToken + serviceToken，然后调用设备列表 API。

  与 aiohttp 硬发 HTTP 相比，这种方式：
  - 共享同一个 deviceId / UA / TLS 指纹
  - 验证码通过后的 Cookie 立即对后续请求生效
  - 不会出现"浏览器验证了但 Python 还是未验证"的脱节

【适用平台】macOS (Apple Silicon / Intel) / Windows 10/11 / Linux
【依赖】pip install selenium webdriver-manager requests

用法：
    # === macOS / Linux ===
    cd tools/mi
    pip install selenium webdriver-manager requests
    python3 browser_token_extract.py

    # 脚本会自动打开 Chrome 窗口，你在里面登录并完成验证
    # 登录成功后回到终端按 Enter，脚本自动抓取 Token 并输出设备列表
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("请先安装依赖: pip install selenium webdriver-manager")
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

import requests

# ======================================================================
# CONFIG
# ======================================================================
# 小米 MiIO 设备列表 API（走 xiaomiio sid，同一套 Cookie 也能用）
MIIO_DEVICE_LIST_URL = "https://api.io.mi.com/app/home/device_list"

# 小米账号登录页（登录后会在 Cookie 里留下 passToken / serviceToken）
# 我们选择直接打开 MiIO 服务的登录授权页，登录完浏览器会自动跳转
# 并在 Cookie 中留下 sid=xiaomiio 的 serviceToken
MI_LOGIN_URL = (
    "https://account.xiaomi.com/fe/service/login/password"
    "?sid=xiaomiio"
    "&_json=true"
    "&_locale=zh_CN"
)

# 备选：如果上面的 URL 404 或改版，试这个通用登录入口
MI_LOGIN_URL_FALLBACK = "https://account.xiaomi.com"

# 音箱过滤关键字
SPEAKER_KEYWORDS = ("speaker", "lx")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# ======================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("browser_token_extract")


def create_driver() -> webdriver.Chrome:
    """创建 Chrome WebDriver，自动下载对应版本的 chromedriver"""
    options = Options()
    # 不使用 headless，因为需要用户手动完成验证
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # 设置窗口大小（小窗口方便操作）
    options.add_argument("--window-size=500,700")

    if ChromeDriverManager:
        service = Service(ChromeDriverManager().install())
    else:
        # 如果 webdriver-manager 没装好，假设 chromedriver 在 PATH 里
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)
    # 移除 navigator.webdriver 标记，降低被检测为自动化的概率
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def extract_cookies_from_browser(driver: webdriver.Chrome) -> dict:
    """从浏览器中提取所有与 xiaomi.com / mi.com 相关的 Cookie"""
    cookies = driver.get_cookies()
    cookie_dict = {}
    for c in cookies:
        cookie_dict[c["name"]] = c["value"]
    return cookie_dict


def get_service_token_from_cookies(cookies: dict) -> tuple[str, str]:
    """
    从 Cookie 中提取 serviceToken 和 userId。

    小米的 Cookie 命名规则：
      - serviceToken: 该服务的 token（如 serviceToken_xiaomiio）
      - userId: 用户 ID（有时是 cUserId）
      - passToken: 全局 passToken（可以兑换其他 sid 的 token）
    """
    service_token = None
    user_id = None
    pass_token = None

    for key, value in cookies.items():
        if "serviceToken" in key and value:
            service_token = value
            log.info("找到 serviceToken (key=%s, len=%d)", key, len(value))
        if key in ("userId", "cUserId") and value:
            user_id = value
            log.info("找到 userId: %s", value)
        if key == "passToken" and value:
            pass_token = value
            log.info("找到 passToken (len=%d)", len(value))

    return service_token, user_id, pass_token


def fetch_device_list(service_token: str, user_id: str) -> list[dict]:
    """用已认证的 serviceToken + userId 拉取 MiIO 设备列表"""
    headers = {
        "Cookie": f"serviceToken={service_token}; userId={user_id}",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"getVirtualModel": "false", "getHuamiDevices": "0"}

    resp = requests.post(MIIO_DEVICE_LIST_URL, headers=headers, data=data, timeout=15)
    resp.raise_for_status()

    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"API 返回错误: {result}")

    return result.get("result", {}).get("list", [])


def fetch_device_list_via_passtoken(pass_token: str, user_id: str) -> list[dict]:
    """
    备用方法：如果 serviceToken 拿不到，先用 passToken 换一个 serviceToken，
    再去拉设备列表。
    """
    # Step 1: 用 passToken 去获取 xiaomiio 服务的 serviceToken
    login_url = (
        "https://account.xiaomi.com/pass/serviceLogin"
        "?sid=xiaomiio"
        "&_json=true"
    )
    headers = {
        "Cookie": f"passToken={pass_token}; userId={user_id}",
        "User-Agent": (
            "Android-7.1.1-1.0.0-ONEPLUS A3010-136-"
            f"{user_id} APP/xiaomi.smarthome APPV/62830"
        ),
    }
    resp = requests.get(login_url, headers=headers, timeout=15)
    # 解析 &&&START&&& 前缀的 JSON 响应
    text = resp.text.replace("&&&START&&&", "").strip()
    data = json.loads(text)

    if "location" not in data:
        raise RuntimeError(
            f"passToken 换 serviceToken 失败，可能 passToken 已过期: {data}"
        )

    # Step 2: 跟随 location 获取 serviceToken（在 Set-Cookie 里）
    location = data["location"]
    resp2 = requests.get(location, headers=headers, allow_redirects=False, timeout=15)
    new_service_token = None
    for cookie_item in resp2.cookies:
        if "serviceToken" in cookie_item.name:
            new_service_token = cookie_item.value
            break

    if not new_service_token:
        raise RuntimeError("未能从 location 跳转中获取 serviceToken")

    log.info("通过 passToken 成功兑换了 xiaomiio 的 serviceToken")
    return fetch_device_list(new_service_token, user_id)


def print_results(devices: list[dict]) -> None:
    """打印设备列表，高亮音箱"""
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
        print("JSON（复制到 xiaogpt-server/config.json）：")
        print("-" * 100)
        export = [
            {
                "hardware": s.get("model"),
                "mi_did": s.get("did"),
                "mi_token": s.get("token"),
            }
            for s in speakers
        ]
        print(json.dumps(export, ensure_ascii=False, indent=2))

    # 保存完整的设备列表到文件备查
    output_file = Path("mi_devices_full.json")
    output_file.write_text(json.dumps(devices, ensure_ascii=False, indent=2))
    log.info("完整设备列表已保存到: %s", output_file.resolve())


def main() -> None:
    print(
        "\n"
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║  小米 Token 提取器（浏览器模式）                                 ║\n"
        "║                                                                  ║\n"
        "║  接下来会自动打开 Chrome 窗口：                                   ║\n"
        "║    1. 你在窗口中登录小米账号                                      ║\n"
        "║    2. 完成滑块/短信验证                                           ║\n"
        "║    3. 登录成功后（看到跳转或首页），回到终端按 Enter               ║\n"
        "║                                                                  ║\n"
        "║  脚本会从浏览器 Cookie 中提取 Token 并查询设备列表               ║\n"
        "╚══════════════════════════════════════════════════════════════════╝\n"
    )

    log.info("正在启动 Chrome 浏览器 ...")
    driver = create_driver()

    try:
        # 打开小米登录页
        log.info("打开小米登录页: %s", MI_LOGIN_URL)
        driver.get(MI_LOGIN_URL)

        # 等待用户登录
        print()
        input(
            "👉 请在打开的 Chrome 窗口中完成登录（包括滑块/验证码）。\n"
            "   登录成功后，回到这里按 Enter 继续 ..."
        )

        # 有时候登录成功后 URL 会跳转，给一点时间让 Cookie 写入
        time.sleep(2)

        # 提取 Cookie
        log.info("正在从浏览器提取 Cookie ...")
        cookies = extract_cookies_from_browser(driver)
        log.info("提取到 %d 个 Cookie", len(cookies))

        if not cookies:
            log.error("未提取到任何 Cookie，请确认已经登录成功。")
            sys.exit(1)

        # 获取关键 Token
        service_token, user_id, pass_token = get_service_token_from_cookies(cookies)

        # 尝试直接用 serviceToken 拉设备列表
        devices = None

        if service_token and user_id:
            log.info("使用 serviceToken 直接查询设备列表 ...")
            try:
                devices = fetch_device_list(service_token, user_id)
            except Exception as e:
                log.warning("serviceToken 方式失败: %s，尝试 passToken 方式 ...", e)

        if not devices and pass_token and user_id:
            log.info("使用 passToken 兑换 xiaomiio serviceToken ...")
            try:
                devices = fetch_device_list_via_passtoken(pass_token, user_id)
            except Exception as e:
                log.error("passToken 方式也失败: %s", e)

        if not devices:
            log.error(
                "\n所有方式均失败。请确认：\n"
                "  1. 浏览器中已经完全登录成功（URL 不再是登录页）\n"
                "  2. 如果用的是国际版小米账号，可能需要切换 API 域名\n"
                "  3. 尝试在浏览器地址栏直接访问 https://home.mi.com 看是否已登录\n"
                "\n提取到的 Cookie 如下（供排查）：\n"
            )
            for k, v in sorted(cookies.items()):
                if any(x in k.lower() for x in ["token", "user", "pass", "service"]):
                    print(f"  {k} = {v[:20]}...")
            sys.exit(1)

        print_results(devices)

        # 额外：尝试把完整的认证信息保存为 .mi.token 格式
        # 这样后续 miservice / xiaogpt 可以复用
        mi_token_data = {
            "userId": user_id,
            "serviceToken": service_token or "",
            "passToken": pass_token or "",
        }
        mi_token_path = Path.home() / ".mi.token"
        mi_token_path.write_text(json.dumps(mi_token_data, indent=2))
        log.info("登录态已保存到 %s（后续 xiaogpt 可直接复用）", mi_token_path)

    finally:
        log.info("关闭浏览器 ...")
        driver.quit()


if __name__ == "__main__":
    main()
