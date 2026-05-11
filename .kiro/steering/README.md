# Kiro Steering 规则索引

本目录存放项目的"人格/场景转向"规则。每个文件对应一个场景，使用 `inclusion: manual`，需要时手动引用，避免相互干扰。

## 已配置场景

| 场景 | 文件 | 触发方式 | 适用话题 |
|---|---|---|---|
| **量化交易** | `quant-trading.md` | `#quant-trading` | 交易所 API、策略、逃顶预警、BTC/SOL/LINK/NVDA/AAPL |
| **AI 微信小程序** | `wechat-miniapp-ai.md` | `#wechat-miniapp-ai` | 小程序后端、LLM 接入、鉴权、流式对话、星座/测试类 |
| **跨平台运维** | `devops-crossplatform.md` | `#devops-crossplatform` | 部署、Remote-SSH、Docker、macOS/Windows 脚本 |

## 使用方法

在与 Kiro 对话时，**引用对应文件** 即可激活该人格，例如：

> `#quant-trading` 帮我写一个 Binance 的 BTC 逃顶监控脚本

Kiro 看到 `#quant-trading` 会自动加载 `quant-trading.md` 的全部规则，按资深量化工程师的身份回答；切换场景只需换引用名即可，规则不会交叉污染。

## 维护说明

- 新增场景：在本目录新建 `<scene-name>.md`，文件头加上 `inclusion: manual` front-matter。
- 修改规则：直接编辑对应文件，下次引用时自动生效。
- 临时合并：一条消息里可以同时引用多个 steering，例如 `#quant-trading #devops-crossplatform` 适用于"部署一个量化策略到服务器"这种混合场景。
