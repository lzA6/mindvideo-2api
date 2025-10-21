# /app/utils/security.py
import time
import uuid
import hashlib
import json
from app.core.config import settings

class MindVideoSigner:
    """
    生成 MindVideo.ai API 所需的 i-sign 动态签名。
    """
    def generate_sign(self) -> str:
        """
        生成包含 nonce, timestamp 和 sign 的 JSON 字符串。
        """
        nonce = str(uuid.uuid4().hex)[:16]
        timestamp = int(time.time() * 1000)
        
        # 根据逆向工程分析，签名的生成逻辑
        sign_str = f"nonce={nonce}&timestamp={timestamp}&app_key={settings.SIGN_APP_KEY}"
        
        # 使用 MD5 哈希算法
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        
        sign_data = {
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign
        }
        
        # 返回紧凑的 JSON 字符串
        return json.dumps(sign_data, separators=(',', ':'))
