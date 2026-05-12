# xiaogpt-server

用 Docker Compose 部署 [xiaogpt](https://github.com/yihong0618/xiaogpt)，让你的小爱音箱接入大语言模型。

## 前置条件

- 已安装 Docker Engine 20+ 和 Docker Compose v2
  - macOS：推荐 [OrbStack](https://orbstack.dev/) 或 Colima，比 Docker Desktop 轻
  - Linux：`curl -fsSL https://get.docker.com | sh`
  - Windows：Docker Desktop + WSL2
- 已通过 `tools/mi/get_mi_info.py` 拿到音箱的 **hardware / mi_did / mi_token**
- 已有 OpenAI API Key（或兼容的中转 Key）

## 目录结构

```
xiaogpt-server/
├── docker-compose.yml      # 容器编排
├── config.json             # 真实凭据（被 .gitignore 排除，不会入库）
├── config.example.json     # 模板，含 <YOUR_*> 占位符
└── README.md               # 本文件
```

## 配置字段说明

| 字段 | 说明 | 来源 |
|---|---|---|
| `hardware` | 音箱型号（如 `xiaomi.wifispeaker.lx06`） | `get_mi_info.py` 输出的 `hardware` |
| `account` | 小米账号（手机号 / 邮箱 / 小米 ID） | 你自己 |
| `password` | 小米账号密码 | 你自己 |
| `mi_did` | 设备 DID | `get_mi_info.py` 输出的 `mi_did` |
| `mi_token` | 设备 Token | `get_mi_info.py` 输出的 `token` |
| `openai_key` | OpenAI API Key，以 `sk-` 开头 | [platform.openai.com](https://platform.openai.com/api-keys) |
| `bot` | 机器人后端，默认 `chatgptapi` | xiaogpt 支持 `chatgptapi`/`glm`/`qwen`/`kimi` 等 |
| `mute_xiaoai` | 是否屏蔽小爱原生回复 | 推荐 `true`，避免双重回答 |
| `keyword` | 触发 LLM 的关键词列表 | 按需定制 |
| `prompt` | 系统提示词 | 当前已针对语音播报优化（禁止 Markdown） |

## 启动

```bash
# === macOS / Linux ===
cd xiaogpt-server

# 首次运行：从模板复制一份，并把真实凭据填进去
# cp config.example.json config.json
# vim config.json   # 替换 <YOUR_MI_ACCOUNT> 等占位符

# 拉镜像并后台启动
docker compose pull
docker compose up -d

# 查看实时日志
docker compose logs -f xiaogpt
```

```powershell
# === Windows 10/11 - PowerShell 7+ (WSL2 内操作，或 Docker Desktop 直接用) ===
cd xiaogpt-server
docker compose pull
docker compose up -d
docker compose logs -f xiaogpt
```

## 常用命令

```bash
docker compose ps             # 查看容器状态
docker compose restart xiaogpt  # 改完 config.json 后重启生效
docker compose down           # 停止并移除容器（镜像保留）
docker compose down -v        # 一并清掉卷（如有）
docker compose pull && docker compose up -d  # 升级到 latest
```

## 验证成功的标志

1. `docker compose ps` 显示容器 `STATUS = Up`
2. `docker compose logs -f xiaogpt` 出现类似 `"已连接 xxx 音箱"` 的中文输出
3. 对着音箱说一句 **"小爱同学，帮我讲个冷笑话"**，音箱应播报由 LLM 生成的内容

## 排错三连

```bash
# 1) 查日志
docker compose logs --tail=200 xiaogpt

# 2) 查容器是否在跑
docker ps | grep xiaogpt

# 3) 进容器手动验证配置
docker exec -it xiaogpt cat /app/config.json
```

## 安全提示

- `config.json` **已加入 `.gitignore`**，不会被 git 追踪。务必确认 `git status` 里不出现它。
- `mi_token` 和 `openai_key` 是敏感凭据，任何时候不要贴到公开聊天 / Issue / 截图里。
- 若怀疑凭据泄漏：立刻修改小米账号密码（会自动作废 mi_token），并到 OpenAI 控制台 Revoke Key。
