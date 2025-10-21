# /app/core/config.py
import os
import uuid
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional, List, Dict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra="ignore"
    )

    APP_NAME: str = "mindvideo-2api"
    APP_VERSION: str = "1.0.0"
    DESCRIPTION: str = "一个将 mindvideo.ai 视频生成功能转换为兼容 OpenAI 格式 API 的高性能代理。"

    # --- 核心安全与部署配置 ---
    API_MASTER_KEY: Optional[str] = "1"
    NGINX_PORT: int = 8088
    
    # --- MindVideo.ai 凭证 ---
    MINDVIDEO_AUTH_TOKENS: List[str] = []

    # --- 签名密钥 ---
    SIGN_APP_KEY: str = "s#c_120*AB"

    # --- 任务轮询配置 ---
    API_REQUEST_TIMEOUT: int = 300
    POLLING_INTERVAL: int = 5 # 秒
    POLLING_TIMEOUT: int = 480 # 秒 (8分钟)

    # --- 模型配置 ---
    MODEL_MAPPING: Dict[str, int] = {
        "sora-2-free": 153
    }
    DEFAULT_MODEL: str = "sora-2-free"

    @model_validator(mode='after')
    def validate_settings(self) -> 'Settings':
        # 从环境变量 MINDVIDEO_AUTH_TOKEN_1, MINDVIDEO_AUTH_TOKEN_2, ... 加载 tokens
        i = 1
        while True:
            token = os.getenv(f"MINDVIDEO_AUTH_TOKEN_{i}")
            if token:
                self.MINDVIDEO_AUTH_TOKENS.append(token)
                i += 1
            else:
                break
        
        if not self.MINDVIDEO_AUTH_TOKENS:
            raise ValueError("必须在 .env 文件中至少配置一个有效的 MINDVIDEO_AUTH_TOKEN_1")
        
        return self

settings = Settings()
