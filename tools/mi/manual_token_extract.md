# 手动提取 MI_DID / MI_TOKEN — 终极方案

当所有 Python 脚本都因风控无法从小米云获取 device_list 时，用以下方法手工提取。

---

## 方法 1：你已经有 DID + Token（直接硬编码跳过）

你之前通过 `get_mi_info.py` 已经拿到过：

```
hardware:  xiaomi.wifispeaker.lx06
mi_did:    379366058
mi_token:  7259666139336744534f484d6b484368
```

**只要你没改过小米密码**，这个 token 依然有效。直接写死在 `xiaogpt-server/config.json`，
并在 `docker-compose.yml` 中加上 `use_command: true`（走 MiIO 指令通道而非 Mina 轮询）。

修改后的 config.json（关键部分）：
```json
{
  "hardware": "xiaomi.wifispeaker.lx06",
  "account": "15237531333",
  "password": "haiyan520",
  "mi_did": "379366058",
  "mi_token": "7259666139336744534f484d6b484368",
  "use_command": true,
  "verbose": true
}
```

`use_command: true` 让 xiaogpt 通过 MiIO 协议直接给音箱发 TTS 指令，
**完全绕过 Mina 的 device_list 轮询**。

---

## 方法 2：从 `~/.mi.token` 缓存读取

如果之前成功登录过（哪怕一次），token 已经缓存：

```bash
# === macOS / Linux ===
cat ~/.mi.token
# 输出 JSON，包含 userId / serviceToken 等字段
```

```powershell
# === Windows 10/11 - PowerShell 7+ ===
Get-Content "$env:USERPROFILE\.mi.token"
```

---

## 方法 3：curl 直接打 MiIO API（绕过 Python）

从 `~/.mi.token` 提取 `serviceToken` 和 `userId` 后：

```bash
# === macOS / Linux ===
# ⚠️ 替换 <SERVICE_TOKEN> 和 <USER_ID>

curl -s "https://api.io.mi.com/app/home/device_list" \
  -H "Cookie: serviceToken=<SERVICE_TOKEN>; userId=<USER_ID>" \
  -d '{"getVirtualModel":false,"getHuamiDevices":0}' \
  | python3 -m json.tool | grep -B2 -A8 "lx06"
```

如果 `api.io.mi.com` 也 403，尝试国际版（风控可能不同步）：
```bash
curl -s "https://api.io.mi.com/app/home/device_list" \
  -H "Cookie: serviceToken=<SERVICE_TOKEN>; userId=<USER_ID>; locale=en_US" \
  -d '{"getVirtualModel":false,"getHuamiDevices":0}' \
  | python3 -m json.tool
```

---

## 方法 4：米家 App 日志提取 DID

### Android
1. 米家 App → 长按小爱音箱 → 设备详情
2. 记录设备 ID（纯数字，即 DID）

### iOS
1. 米家 App → 我的 → 设置 → 关于 → 连续点版本号 10 次开启开发者模式
2. 设置 → 开发者选项 → 设备信息日志 → 找到 lx06

---

## 方法 5：抓包（最可靠但最折腾）

### macOS 推荐 Proxyman

```bash
# === macOS ===
brew install --cask proxyman
```

1. 开 Proxyman → 启用 HTTPS 解密
2. iPhone 代理指向 Mac mini IP:9090
3. iPhone 安装 Proxyman CA 证书并信任
4. 打开**小爱音箱 App**（不是米家）→ 点一下音箱
5. Proxyman 搜索 `mina.mi.com` 或 `io.mi.com`
6. Response 里有 `did` + `token`

### 替代工具
- Charles Proxy（跨平台）
- mitmproxy：`brew install mitmproxy && mitmweb`

---

## 风控解封加速操作清单

1. **立刻停容器**：`docker compose down`
2. **删 token 缓存**：`rm ~/.mi.token`
3. **换 IP**：用一个之前从没发过请求的手机热点
4. **等 12-24 小时**：期间不要再跑任何登录脚本
5. **解封后的第一件事**：给 docker-compose.yml 加 token 持久化挂载

```yaml
# docker-compose.yml
services:
  xiaogpt:
    image: yihong0618/xiaogpt:latest
    container_name: xiaogpt
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./config.json:/app/config.json
      - ./.mi.token:/root/.mi.token    # ← 关键！持久化 token，避免每次重启都重新登录
```

这样 **即使容器重启也不会触发新的登录请求**。
