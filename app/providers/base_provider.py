# /app/providers/base_provider.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from fastapi.responses import JSONResponse

class BaseProvider(ABC):
    """
    定义视频/图像生成提供者的基础接口。
    """
    @abstractmethod
    async def generate_video(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理视频生成的核心方法。
        """
        pass

    @abstractmethod
    async def get_models(self) -> Dict[str, Any]:
        """
        获取可用模型列表的方法。
        """
        pass
