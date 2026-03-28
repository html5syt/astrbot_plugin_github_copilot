# GitHub Copilot 接入插件

将 GitHub Copilot 作为一个独立的大语言模型提供商接入 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 中。你可以通过本插件把 GitHub Copilot 作为对话模型来使用。

> **注意**：本插件需要你拥有一个有效的 GitHub Copilot 订阅，**且不能用于高频请求，否则会被限制请求速率或封号！**

## 特性
- ✅ **代理转接**：内部提供一个微型 OpenAI 兼容 API 服务器，收发转接请求，自由配置端口和 Key。
- ✅ **流式输出**：原生兼容大模型流式（Streaming）对话模式。
- ✅ **自动授权**：支持通过 `/copilot_login` 使用 Device Auth 流自动登录，无需手动抓包抓取 Token。
- ✅ **配额查询**：自带 `/copilot_usage` 指令，查询你的 Copilot 状态，包括最新的“高级模型请求（Premium Requests）”额度信息。
- ✅ **嵌入模型**：支持调用 Copilot 原本用于 VS Code 设置搜索的嵌入向量模型，适用于语义搜索等场景。

## 使用
1. 机器人启动后，插件自动在后台启动兼容器，默认监听 `http://127.0.0.1:8089/v1`，默认 API Key 为 `sk-copilot`。
2. 在 WebUI 的插件管理中可以修改该微型服务器的 host、port 端口号及内网连接使用的 api_key，也可修改 Github Token `ghu_token`。
3. 如果没有 `ghu_token`，在聊天框向机器人发送 `/copilot_login`，并根据提示在浏览器完成授权。
4. 前往 AstrBot WebUI -> 模型提供商 -> 新建一个 **OpenAI (Chat Completion)** 供应商，地址填 `http://127.0.0.1:8089/v1`（对应你的配置），密钥填 `sk-copilot`。
5. 保存后即可将模型设置为 `gpt-4` 等开始无缝对话。
6. 随时可通过 `/copilot_usage` 查询你的高级配额。
