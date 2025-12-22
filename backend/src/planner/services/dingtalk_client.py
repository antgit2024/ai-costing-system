from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests

from ...config import settings


@dataclass
class DingTalkAttachment:
    content: bytes
    headers: dict[str, str]


class DingTalkClient:
    TOKEN_URL = "https://oapi.dingtalk.com/gettoken"

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        system_token: str,
        app_type: str,
        user_id: str,
        session: Optional[requests.Session] = None,
    ):
        self.app_key = app_key
        self.app_secret = app_secret
        self.system_token = system_token
        self.app_type = app_type
        self.user_id = user_id
        self._session = session or requests.Session()
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0.0

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expire_at:
            return self._access_token

        params = {"appkey": self.app_key, "appsecret": self.app_secret}
        resp = self._session.get(self.TOKEN_URL, params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errcode") != 0:
            raise RuntimeError(f"Failed to obtain DingTalk access token: {payload}")

        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 7200)
        self._token_expire_at = time.time() + max(0, expires_in - 300)
        return self._access_token

    def _temporary_url_endpoint(self) -> str:
        # DingTalk openapi: yida temporaryUrls is a GET endpoint and appType is part of the path
        return f"https://api.dingtalk.com/v1.0/yida/apps/temporaryUrls/{self.app_type}"

    @staticmethod
    def _pick_url(data: Any) -> Optional[str]:
        if isinstance(data, str) and data:
            return data
        if not isinstance(data, dict):
            return None
        # common success wrapper: {"result": "<url>"}
        result0 = data.get("result")
        if isinstance(result0, str) and result0:
            return result0
        for key in ("downloadUrl", "temporaryUrl", "url"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
        result = data.get("result") or data.get("data")
        if isinstance(result, dict):
            for key in ("downloadUrl", "temporaryUrl", "url"):
                val = result.get(key)
                if isinstance(val, str) and val:
                    return val
        if isinstance(result, list) and result:
            for item in result:
                if isinstance(item, dict):
                    for key in ("downloadUrl", "temporaryUrl", "url"):
                        val = item.get(key)
                        if isinstance(val, str) and val:
                            return val
        return None

    def get_temporary_download_url(self, file_url: str) -> str:
        token = self._get_access_token()
        headers = {"x-acs-dingtalk-access-token": token}
        params = {
            "systemToken": self.system_token,
            "userId": self.user_id,
            "fileUrl": file_url,
        }
        resp = self._session.get(self._temporary_url_endpoint(), headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        url = self._pick_url(data)
        if not url:
            raise RuntimeError(f"Failed to get temporary url: {json.dumps(data, ensure_ascii=False)[:600]}")
        return url

    def download_attachment(self, file_url: str) -> DingTalkAttachment:
        temp_url = self.get_temporary_download_url(file_url)
        resp = self._session.get(temp_url, timeout=30)
        resp.raise_for_status()
        headers = {k: v for k, v in resp.headers.items()}
        return DingTalkAttachment(content=resp.content, headers=headers)


def get_dingtalk_client() -> DingTalkClient:
    cfg_path = Path(settings.yida_materials_config_path)
    if not cfg_path.exists():
        raise RuntimeError(f"YiDa materials config not found: {cfg_path}")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    for k in ("app_key", "app_secret", "system_token", "app_type", "user_id"):
        if not data.get(k):
            raise RuntimeError(f"Missing DingTalk config field: {k}")
    return DingTalkClient(
        app_key=data["app_key"],
        app_secret=data["app_secret"],
        system_token=data["system_token"],
        app_type=data["app_type"],
        user_id=data["user_id"],
    )


