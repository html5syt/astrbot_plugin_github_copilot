import re

with open(
    "d:\\Projects\\Python-Project\\astrbot_plugin_github_copilot\\main.py",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

# Find the start of the function
start_marker = '    @filter.command("copilot_usage")'
end_marker = "    async def terminate(self):"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_func = '''    @filter.command("copilot_usage")
    async def copilot_usage(self, event: AstrMessageEvent):
        """查询 GitHub Copilot 当前订阅和内部 Token 状态"""
        ghu_token = self.config.get("ghu_token", "")
        if not ghu_token or ghu_token == "YOUR_GITHUB_COPILOT_TOKEN_HERE":
            yield event.plain_result("未配置有效 `ghu_token`。请在 /copilot_login 授权或修改配置文件。")
            return

        yield event.plain_result("正在查询 GitHub Copilot 订阅状态，请稍后...")

        headers_user = {
            "Authorization": f"token {ghu_token}" if ghu_token.startswith("gho_") else f"Bearer {ghu_token}",
            "Accept": "application/json",
            "User-Agent": "GitHubCopilotChat/0.35.0",
            "Editor-Version": "vscode/1.107.0",
            "Editor-Plugin-Version": "copilot-chat/0.35.0",
        }

        user_info = {"user": "Unknown", "sku": "Unknown", "chat_enabled": False}
        limits_info = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.github.com/copilot_internal/user", headers=headers_user) as user_resp:
                    if user_resp.status == 200:
                        user_data = await user_resp.json()
                        user_info.update({
                            "user": user_data.get("login", "Unknown"),
                            "sku": user_data.get("access_type_sku", "Unknown"),
                            "chat_enabled": user_data.get("chat_enabled", False)
                        })

                        quota = user_data.get("quota_snapshots", {})
                        for key, label in [("chat", "基础请求(Core)"), ("premium_interactions", "高级请求(Advanced)")]:
                            q_data = quota.get(key, {})
                            if not q_data:
                                limits_info.append(f"{label}: 无限制 (Unlimited 或当前接口未返回)")
                            elif q_data.get("unlimited"):
                                limits_info.append(f"{label}: 无限制 (Unlimited)")
                            else:
                                total, remaining = q_data.get("entitlement", 0), q_data.get("remaining", 0)
                                limits_info.append(f"{label}: {total - remaining} / {total} (剩余 {remaining})")

                        if reset_date := user_data.get("quota_reset_date"):
                            limits_info.append(f"配额重置时间: {reset_date}")

            if not limits_info or user_info["user"] == "Unknown":
                success, result = await self._fetch_copilot_token_info(ghu_token)
                if not success:
                    yield event.plain_result(f"❌ 查询失败，Token 可能已失效。\\n原因: {result}")
                    return

                user_info.update({
                    "sku": result.get("sku", "Unknown"),
                    "user": result.get("user", "Unknown"),
                    "chat_enabled": result.get("chat_enabled", False)
                })

                if not limits_info:
                    headers_models = {
                        "Authorization": f"Bearer {result.get('token')}",
                        "User-Agent": "GitHubCopilotChat/0.35.0",
                        "Editor-Version": "vscode/1.107.0",
                        "Editor-Plugin-Version": "copilot-chat/0.35.0",
                    }
                    async with aiohttp.ClientSession() as fallback_session:
                        async with fallback_session.get("https://api.githubcopilot.com/models", headers=headers_models) as models_resp:
                            hw = lambda k: models_resp.headers.get(k)
                            
                            limits_to_check = [
                                ("基础请求(Core)", "core"),
                                ("高级请求(Advanced)", "advanced")
                            ]
                            for label, kind in limits_to_check:
                                rem = hw(f"x-ratelimit-user-chat-{kind}-requests-remaining") or hw(f"x-ratelimit-user-{kind}-remaining")
                                tot = hw(f"x-ratelimit-user-chat-{kind}-requests-limit") or hw(f"x-ratelimit-user-{kind}-limit")
                                
                                if rem is not None and tot is not None:
                                    limits_info.append(f"{label}: {int(tot) - int(rem)} / {tot} (剩余 {rem})")
                                else:
                                    limits_info.append(f"{label}: 无限制 (Unlimited 或当前接口未返回)")

            advanced_limits_str = "\\n".join(["🚀 " + item for item in limits_info])

        except Exception as e:
            advanced_limits_str = f"🚀 额度查询失败 ({e})"

        msg = (
            "👩‍💻 **GitHub Copilot 状态信息**\\n"
            f"👤 用户：{user_info['user']}\\n"
            f"📦 订阅类型：{user_info['sku']}\\n"
            f"{advanced_limits_str}\\n"
            f"💬 Chat权限：{'✅ 允许' if user_info['chat_enabled'] else '❌ 拒绝'}"
        )
        yield event.plain_result(msg)

'''

    new_content = content[:start_idx] + new_func + content[end_idx:]
    with open(
        "d:\\Projects\\Python-Project\\astrbot_plugin_github_copilot\\main.py",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(new_content)
    print("Replace done.")
else:
    print("Markers not found.")
