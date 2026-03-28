import os
import time
import json
import asyncio
import aiohttp
from aiohttp import web

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig


class CopilotLocalServer:
    def __init__(self, plugin, host: str, port: int, api_key: str):
        self.plugin = plugin
        self.host = host
        self.port = port
        self.api_key = api_key
        self.app = web.Application(
            client_max_size=1024**2 * 100
        )  # 100MB limit for image uploads
        self.app.router.add_post("/v1/chat/completions", self.handle_chat)
        self.app.router.add_get("/v1/models", self.handle_models)
        self.app.router.add_post("/v1/embeddings", self.handle_embeddings)
        self.runner = None
        self.site = None

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

    async def stop(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def handle_models(self, request):
        try:
            token = await self.plugin.get_session_token()
        except Exception as e:
            return web.json_response(
                {"error": f"Failed to acquire Copilot internal token: {e}"}, status=401
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Editor-Version": "vscode/1.107.0",
            "Editor-Plugin-Version": "copilot-chat/0.35.0",
            "OpenAI-Organization": "github-copilot",
            "OpenAI-Intent": "conversation-panel",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.githubcopilot.com/models",
                headers=headers,
            ) as copilot_resp:
                if copilot_resp.status != 200:
                    return web.json_response(
                        {
                            "error": f"HTTP {copilot_resp.status}: {await copilot_resp.text()}"
                        },
                        status=copilot_resp.status,
                    )
                data = await copilot_resp.json()

                # Format to OpenAI standard if necessary
                if "data" in data:
                    for model in data["data"]:
                        model.setdefault("object", "model")
                        model.setdefault("created", 1700000000)
                        model.setdefault("owned_by", "github-copilot")
                else:
                    # fallback just in case
                    data["object"] = "list"
                    data.setdefault("data", [])

                return web.json_response(data)

    async def handle_chat(self, request):
        auth = request.headers.get("Authorization", "")
        if self.api_key and auth != f"Bearer {self.api_key}":
            return web.json_response({"error": "Unauthorized proxy access"}, status=401)

        try:
            req_data = await request.json()
        except Exception as e:  # Broad except for python syntax robustness
            logger.error(f"Invalid JSON payload in handle_chat: {e}")
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        try:
            token = await self.plugin.get_session_token()
        except Exception as e:
            return web.json_response(
                {"error": f"Failed to acquire Copilot internal token: {e}"}, status=401
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Editor-Version": "vscode/1.85.0",
            "Editor-Plugin-Version": "copilot-chat/0.35.0",
            "OpenAI-Organization": "github-copilot",
            "OpenAI-Intent": "conversation-panel",
            "Content-Type": "application/json",
        }

        model = req_data.get("model", "gpt-4")
        if model == "github_copilot":
            model = "gpt-4"

        payload = {
            "model": model,
            "messages": req_data.get("messages", []),
            "stream": req_data.get("stream", False),
            "temperature": req_data.get("temperature", 0.5),
        }

        if "tools" in req_data:
            payload["tools"] = req_data["tools"]
        if "tool_choice" in req_data:
            payload["tool_choice"] = req_data["tool_choice"]

        if payload["stream"]:
            resp = web.StreamResponse(
                status=200, reason="OK", headers={"Content-Type": "text/event-stream"}
            )
            await resp.prepare(request)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.githubcopilot.com/chat/completions",
                    headers=headers,
                    json=payload,
                ) as copilot_resp:
                    if copilot_resp.status != 200:
                        err_text = await copilot_resp.text()
                        await resp.write(
                            f"data: {json.dumps({'error': f'Github Copilot HTTP {copilot_resp.status}: {err_text}'})}\n\n".encode(
                                "utf-8"
                            )
                        )
                        await resp.write(b"data: [DONE]\n\n")
                        return resp

                    async for line in copilot_resp.content:
                        await resp.write(line)
            return resp
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.githubcopilot.com/chat/completions",
                    headers=headers,
                    json=payload,
                ) as copilot_resp:
                    if copilot_resp.status != 200:
                        return web.json_response(
                            {
                                "error": f"HTTP {copilot_resp.status}: {await copilot_resp.text()}"
                            },
                            status=copilot_resp.status,
                        )
                    data = await copilot_resp.json()
                    return web.json_response(data)

    async def handle_embeddings(self, request):
        auth = request.headers.get("Authorization", "")
        if self.api_key and auth != f"Bearer {self.api_key}":
            return web.json_response({"error": "Unauthorized proxy access"}, status=401)

        try:
            req_data = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON payload in handle_embeddings: {e}")
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        try:
            ghu_token = self.plugin.config.get("ghu_token", "")
            if not ghu_token:
                raise ValueError("No GitHub token configured")
        except Exception as e:
            return web.json_response(
                {"error": f"Failed to acquire GitHub token: {e}"}, status=401
            )

        headers = {
            "Authorization": f"Bearer {ghu_token}",
            "User-Agent": "GitHubCopilotChat/0.41.2",
            "x-client-application": "vscode/1.113.0",
            "x-client-source": "copilot-chat/0.41.2",
            "x-github-api-version": "2025-05-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Adapt payload from OpenAI format to internal exact payload format
        input_data = req_data.get("input", "")
        # GitHub expects an array for 'inputs'
        if isinstance(input_data, str):
            inputs_list = [input_data]
        else:
            inputs_list = input_data

        target_model = req_data.get("model", "text-embedding-3-small-512")
        # 兼容处理: 如果传来的是不支持的模型名, fallback
        safe_models = [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-3-small-512",
        ]
        if target_model not in safe_models:
            target_model = "text-embedding-3-small-512"

        payload = {
            "inputs": inputs_list,
            "input_type": "document",
            "embedding_model": target_model,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.github.com/embeddings",
                headers=headers,
                json=payload,
            ) as copilot_resp:
                if copilot_resp.status != 200:
                    return web.json_response(
                        {
                            "error": f"HTTP {copilot_resp.status}: {await copilot_resp.text()}"
                        },
                        status=copilot_resp.status,
                    )
                data = await copilot_resp.json()

                # Convert response shape from GitHub format to OpenAI standard expected Format
                # github returns: {"embeddings": [{"embedding": [...], "index": 0}]}
                # openai expects: {"object": "list", "data": [{"object": "embedding", "embedding": [...], "index": 0}]}
                resp_payload = {"object": "list", "data": [], "model": target_model}

                if "embeddings" in data:
                    for item in data["embeddings"]:
                        item.setdefault("object", "embedding")
                        resp_payload["data"].append(item)

                return web.json_response(resp_payload)


@register(
    "astrbot_plugin_github_copilot",
    "YourName",
    "通过在本地启动微型Web转化API接入GitHub Copilot，原生兼容支持大模型流式、函数调用以及多模态。",
    "1.0.0",
)
class GithubCopilotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        self.session_token = None
        self.token_expires_at = 0
        self.last_token_info = {}

        self.server = None

    async def initialize(self):
        """Plugin init: start local API Server"""
        host = self.config.get("api_host", "127.0.0.1")
        port = self.config.get("api_port", 8089)
        key = self.config.get("api_key", "sk-copilot")
        self.server = CopilotLocalServer(self, host, port, key)

        try:
            await self.server.start()
            logger.info(
                f"🚀 GitHub Copilot 本地转换 API 已启动: http://{host}:{port}/v1 (鉴权: {key})"
            )
        except Exception as e:
            logger.error(f"❌ GitHub Copilot 本地服务器启动失败 (端口是否被占用?): {e}")

    async def _fetch_copilot_token_info(self, ghu_token: str):
        headers = {
            "Authorization": f"token {ghu_token}"
            if ghu_token.startswith("gho_")
            else f"Bearer {ghu_token}",
            "Accept": "application/json",
            "User-Agent": "GitHubCopilotChat/0.35.0",
            "Editor-Version": "vscode/1.107.0",
            "Editor-Plugin-Version": "copilot-chat/0.35.0",
            "Copilot-Integration-Id": "vscode-chat",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/copilot_internal/v2/token", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return True, data
                else:
                    return False, f"HTTP {resp.status}: {await resp.text()}"

    async def get_session_token(self):
        if self.session_token and time.time() < self.token_expires_at:
            return self.session_token

        ghu_token = self.config.get("ghu_token", "")
        if not ghu_token or ghu_token == "YOUR_GITHUB_COPILOT_TOKEN_HERE":
            raise Exception(
                "请检查 `config.json` 的 ghu_token，或通过 /copilot_login 授权。"
            )

        success, result = await self._fetch_copilot_token_info(ghu_token)
        if success:
            self.session_token = result.get("token")
            # 提前 5 分钟刷新
            self.token_expires_at = result.get("expires_at", time.time() + 1800) - 300
            self.last_token_info = result
            return self.session_token
        else:
            raise Exception(f"未能获取 Copilot 内部 Token: {result}")

    @filter.command("copilot_login")
    async def copilot_login(self, event: AstrMessageEvent):
        """通过设备授权(Device Auth)获取 GitHub Copilot 凭据"""
        from .device_auth import get_device_code, poll_access_token

        yield event.plain_result("正在初始化 GitHub 授权流程，请稍候...")
        try:
            device_info = await get_device_code()
            user_code = device_info.get("user_code")
            ver_uri = device_info.get("verification_uri")
            interval = device_info.get("interval", 5)
            device_code = device_info.get("device_code")

            yield event.plain_result(
                f"🔑 **GitHub 设备授权**:\n请在浏览器打开以下链接:\n{ver_uri}\n\n👉 输入验证码: {user_code}\n\n(等待您完成授权，超时15分钟)"
            )

            github_token = await asyncio.wait_for(
                poll_access_token(device_code, interval), timeout=900
            )

            # 保存到配置
            self.config["ghu_token"] = github_token
            self.config.save_config()

            yield event.plain_result("🎉 授权成功！GitHub 凭据已被更新。")
            self.session_token = None

        except asyncio.TimeoutError:
            yield event.plain_result("❌ 授权超时。如果需要请重新触发指令。")
        except Exception as e:
            yield event.plain_result(f"❌ 授权中发生错误: {str(e)}")

    @filter.command("copilot_usage")
    async def copilot_usage(self, event: AstrMessageEvent):
        """查询 GitHub Copilot 当前订阅和内部 Token 状态"""
        ghu_token = self.config.get("ghu_token", "")
        if not ghu_token or ghu_token == "YOUR_GITHUB_COPILOT_TOKEN_HERE":
            yield event.plain_result(
                "未配置有效 `ghu_token`。请在 /copilot_login 授权或修改配置文件。"
            )
            return

        yield event.plain_result("正在查询 GitHub Copilot 订阅状态，请稍后...")

        headers_user = {
            "Authorization": f"token {ghu_token}"
            if ghu_token.startswith("gho_")
            else f"Bearer {ghu_token}",
            "Accept": "application/json",
            "User-Agent": "GitHubCopilotChat/0.35.0",
            "Editor-Version": "vscode/1.107.0",
            "Editor-Plugin-Version": "copilot-chat/0.35.0",
        }

        user_info = {"user": "Unknown", "sku": "Unknown", "chat_enabled": False}
        limits_info = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/copilot_internal/user", headers=headers_user
                ) as user_resp:
                    if user_resp.status == 200:
                        user_data = await user_resp.json()
                        user_info.update(
                            {
                                "user": user_data.get("login", "Unknown"),
                                "sku": user_data.get("access_type_sku", "Unknown"),
                                "chat_enabled": user_data.get("chat_enabled", False),
                            }
                        )

                        quota = user_data.get("quota_snapshots", {})
                        for key, label in [
                            ("chat", "基础请求(Core)"),
                            ("premium_interactions", "高级请求(Advanced)"),
                        ]:
                            q_data = quota.get(key, {})
                            if not q_data:
                                limits_info.append(
                                    f"{label}: 无限制 (Unlimited 或当前接口未返回)"
                                )
                            elif q_data.get("unlimited"):
                                limits_info.append(f"{label}: 无限制 (Unlimited)")
                            else:
                                total, remaining = (
                                    q_data.get("entitlement", 0),
                                    q_data.get("remaining", 0),
                                )
                                limits_info.append(
                                    f"{label}: {total - remaining} / {total} (剩余 {remaining})"
                                )

                        if reset_date := user_data.get("quota_reset_date"):
                            limits_info.append(f"配额重置时间: {reset_date}")

            if not limits_info or user_info["user"] == "Unknown":
                success, result = await self._fetch_copilot_token_info(ghu_token)
                if not success:
                    yield event.plain_result(
                        f"❌ 查询失败，Token 可能已失效。\n原因: {result}"
                    )
                    return

                user_info.update(
                    {
                        "sku": result.get("sku", "Unknown"),
                        "user": result.get("user", "Unknown"),
                        "chat_enabled": result.get("chat_enabled", False),
                    }
                )

                if not limits_info:
                    headers_models = {
                        "Authorization": f"Bearer {result.get('token')}",
                        "User-Agent": "GitHubCopilotChat/0.35.0",
                        "Editor-Version": "vscode/1.107.0",
                        "Editor-Plugin-Version": "copilot-chat/0.35.0",
                    }
                    async with aiohttp.ClientSession() as fallback_session:
                        async with fallback_session.get(
                            "https://api.githubcopilot.com/models",
                            headers=headers_models,
                        ) as models_resp:
                            hw = lambda k: models_resp.headers.get(k)

                            limits_to_check = [
                                ("基础请求(Core)", "core"),
                                ("高级请求(Advanced)", "advanced"),
                            ]
                            for label, kind in limits_to_check:
                                rem = hw(
                                    f"x-ratelimit-user-chat-{kind}-requests-remaining"
                                ) or hw(f"x-ratelimit-user-{kind}-remaining")
                                tot = hw(
                                    f"x-ratelimit-user-chat-{kind}-requests-limit"
                                ) or hw(f"x-ratelimit-user-{kind}-limit")

                                if rem is not None and tot is not None:
                                    limits_info.append(
                                        f"{label}: {int(tot) - int(rem)} / {tot} (剩余 {rem})"
                                    )
                                else:
                                    limits_info.append(
                                        f"{label}: 无限制 (Unlimited 或当前接口未返回)"
                                    )

            advanced_limits_str = "\n".join(["🚀 " + item for item in limits_info])

        except Exception as e:
            advanced_limits_str = f"🚀 额度查询失败 ({e})"

        msg = (
            "👩‍💻 **GitHub Copilot 状态信息**\n"
            f"👤 用户：{user_info['user']}\n"
            f"📦 订阅类型：{user_info['sku']}\n"
            f"{advanced_limits_str}\n"
            f"💬 Chat权限：{'✅ 允许' if user_info['chat_enabled'] else '❌ 拒绝'}"
        )
        yield event.plain_result(msg)

    async def terminate(self):
        self.session_token = None
        if self.server:
            await self.server.stop()
