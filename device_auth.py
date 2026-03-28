import aiohttp
import asyncio
from typing import Tuple, Dict

CLIENT_ID = "Iv1.b507a08c87ecfe98"
USER_AGENT = "GitHubCopilotChat/0.35.0"

async def get_device_code() -> Dict:
    url = "https://github.com/login/device/code"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    data = {"client_id": CLIENT_ID, "scope": "read:user"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=data) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status} fetching device code")
            try:
                return await resp.json()
            except Exception as e:
                raise Exception("Failed to decode JSON from GitHub device code response")

async def poll_access_token(device_code: str, interval: int) -> str:
    url = "https://github.com/login/oauth/access_token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    data = {
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
    }
    
    async with aiohttp.ClientSession() as session:
        while True:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status} polling access token")
                try:
                    res = await resp.json()
                except Exception as e:
                    raise Exception("Failed to decode JSON from GitHub access token response")
                    
                if "error" in res:
                    if res["error"] == "authorization_pending":
                        pass
                    elif res["error"] == "slow_down":
                        interval += 5
                    else:
                        raise Exception(res.get("error_description", str(res)))
                elif "access_token" in res:
                    return res["access_token"]
            
            await asyncio.sleep(interval)
