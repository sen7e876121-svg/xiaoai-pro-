# 小爱音箱信息提取工具

一个轻量的命令行脚本，用于从小米云获取账号下的所有设备列表，并自动筛选出 **小爱音箱**（含 `speaker` / `lx` 标识的型号），输出其 **Hardware 型号 / MI_DID / Token**，用于对接：

- [xiaogpt](https://github.com/yihong0618/xiaogpt) — 让小爱接入 ChatGPT / LLM
- [python-miio](https://github.com/rytilahti/python-miio) — 本地控制小米设备
- [Home Assistant](https://www.home-assistant.io/integrations/xiaomi_miio/) — 智能家居集成
- [node-mihome](https://github.com/maxinminax/node-mihome) — Node.js 小米生态

## 适用平台

- macOS (Apple Silicon / Intel)
- Windows 10 / 11
- Linux (Ubuntu 22.04+ / Debian 12+)

## 快速开始

### 1. 克隆仓库并进入目录

```bash
# === 任意平台 ===
git clone https://github.com/sen7e876121-svg/xiaoai-pro-.git
cd xiaoai-pro-/tools/mi
```

### 2. 创建并激活虚拟环境（强烈推荐，避免污染宿主机）

```bash
# === macOS / Linux ===
python3 -m venv .venv
source .venv/bin/activate
```

```powershell
# === Windows 10/11 - PowerShell 7+ ===
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```bash
# === 任意平台 ===
pip install -r requirements.txt
```

### 4. 运行脚本

**方式 A — 环境变量（推荐，账号不入库）**：

```bash
# === macOS / Linux ===
# ⚠️ 替换 <YOUR_USERNAME> 为你的小米账号，<YOUR_PASSWORD> 为你的密码
export MI_USER="<YOUR_USERNAME>"
export MI_PASS="<YOUR_PASSWORD>"
python3 get_mi_info.py
```

```powershell
# === Windows 10/11 - PowerShell 7+ ===
# ⚠️ 替换 <YOUR_USERNAME> 和 <YOUR_PASSWORD>
$env:MI_USER="<YOUR_USERNAME>"
$env:MI_PASS="<YOUR_PASSWORD>"
python .\get_mi_info.py
```

**方式 B — 直接改脚本**：编辑 `get_mi_info.py` 的 `CONFIG` 区，替换 `<YOUR_USERNAME>` / `<YOUR_PASSWORD>` 后运行。**注意不要把改过的脚本 push 到 Git**。

## 输出示例

```
========================================================================================================================
账号 13800000000 下共发现 5 台设备：
------------------------------------------------------------------------------------------------------------------------
[SPEAKER]  小爱音箱Pro             xiaomi.wifispeaker.lx04        DID=1234567890        IP=192.168.1.23     TOKEN=abcdef...
[SPEAKER]  小爱音箱Play            xiaomi.wifispeaker.lx05        DID=1234567891        IP=192.168.1.24     TOKEN=123456...
           米家台灯                yeelink.light.lamp4             DID=1234567892        IP=192.168.1.25     TOKEN=789abc...
========================================================================================================================

命中 2 台小爱音箱：
[
  {
    "name": "小爱音箱Pro",
    "hardware": "xiaomi.wifispeaker.lx04",
    "mi_did": "1234567890",
    "token": "abcdef...",
    ...
  }
]
```

## 常见问题

| 现象 | 处理方式 |
|---|---|
| 登录失败 / 报验证码 | 临时关闭小米账号的二次验证 |
| 卡住无响应 | 删除 `~/.mi.token` 文件后重试 |
| 找不到音箱 | 确认设备已在米家 App 中绑定、已联网 |
| `ModuleNotFoundError: miservice` | 检查是否激活了虚拟环境、`pip install -r requirements.txt` 是否成功 |

## 安全提示

- Token 是控制设备的完整凭据，**请勿泄露、勿提交到公共仓库**
- 建议运行完记下 DID/Token 后，立刻 `unset MI_USER MI_PASS` 清除环境变量
- `~/.mi.token` 缓存文件也含登录态，慎重处理
