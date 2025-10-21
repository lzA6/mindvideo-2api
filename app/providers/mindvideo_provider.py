# /app/providers/mindvideo_provider.py
import time
import asyncio
import threading
import json
from typing import Dict, Any, AsyncGenerator

import cloudscraper
from fastapi import HTTPException
from loguru import logger

from app.core.config import settings
from app.providers.base_provider import BaseProvider
from app.utils.security import MindVideoSigner

class MindVideoProvider(BaseProvider):
    BASE_URL = "https://api.mindvideo.ai/api/v2"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.signer = MindVideoSigner()
        self.token_index = 0
        self.token_lock = threading.Lock()

    def _get_auth_token(self) -> str:
        with self.token_lock:
            token = settings.MINDVIDEO_AUTH_TOKENS[self.token_index]
            self.token_index = (self.token_index + 1) % len(settings.MINDVIDEO_AUTH_TOKENS)
            return token

    def _prepare_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "authorization": f"Bearer {self._get_auth_token()}",
            "i-lang": "zh-CN",
            "i-sign": self.signer.generate_sign(),
            "i-version": "1.0.8",
            "origin": "https://www.mindvideo.ai",
            "referer": "https://www.mindvideo.ai/",
        }

    async def _submit_task(self, payload: Dict[str, Any]) -> int:
        url = f"{self.BASE_URL}/creations"
        headers = self._prepare_headers()
        
        logger.info(f"--- [MindVideoProvider] 提交视频生成任务 ---")
        logger.info(f"URL: POST {url}")
        logger.info(f"Payload: {payload}")
        
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None, 
                lambda: self.scraper.post(url, headers=headers, json=payload, timeout=settings.API_REQUEST_TIMEOUT)
            )
            response.raise_for_status()
            data = response.json()
        except json.JSONDecodeError:
            raise Exception(f"提交任务失败: 无法解析上游响应. 响应内容: {response.text[:200]}")
        except Exception as e:
            logger.error(f"提交任务时发生网络或HTTP错误: {e}")
            raise Exception(f"提交任务失败: {str(e)}")

        logger.info(f"上游响应: {data}")

        if data.get("code") != 0 or "data" not in data or "id" not in data["data"]:
            raise Exception(f"提交任务失败: {data.get('message', '未知错误')}")
        
        task_id = data["data"]["id"]
        logger.info(f"任务提交成功，Task ID: {task_id}")
        return task_id

    async def submit_video_task(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        prompt = request_data.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="参数 'prompt' 不能为空。")

        model_name = request_data.get("model", settings.DEFAULT_MODEL)
        bot_id = settings.MODEL_MAPPING.get(model_name)
        if not bot_id:
            raise HTTPException(status_code=400, detail=f"不支持的模型: '{model_name}'")

        size = request_data.get("size", "720x1280")
        
        payload = {
            "type": 1,
            "bot_id": bot_id,
            "options": {
                "prompt": prompt,
                "size": size,
                "seconds": 15,
                "history_images": []
            },
            "is_public": True,
            "copy_protection": False
        }

        try:
            task_id = await self._submit_task(payload)
            return {"task_id": task_id}
        except Exception as e:
            logger.error(f"提交视频任务时出错: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")

    async def stream_task_progress(self, task_id: int) -> AsyncGenerator[str, None]:
        start_time = time.time()
        url = f"{self.BASE_URL}/creations/task_progress"
        
        try:
            while time.time() - start_time < settings.POLLING_TIMEOUT:
                await asyncio.sleep(settings.POLLING_INTERVAL)
                
                headers = self._prepare_headers()
                params = {"ids[]": task_id}
                
                logger.info(f"--- [MindVideoProvider] 轮询任务状态 (Task ID: {task_id}) ---")
                
                loop = asyncio.get_running_loop()
                try:
                    response = await loop.run_in_executor(
                        None, 
                        lambda: self.scraper.get(url, headers=headers, params=params, timeout=settings.API_REQUEST_TIMEOUT)
                    )
                    response.raise_for_status()
                    data = response.json()
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"轮询状态时发生错误: {e}")
                    continue

                logger.info(f"轮询响应: {data}")

                if data.get("code") != 0 or not data.get("data"):
                    logger.warning(f"轮询状态异常: {data.get('message')}")
                    continue

                task_data = data["data"][0]
                status = task_data.get("task_status")
                progress = int(task_data.get('task_progress', 0))
                remark = task_data.get('task_remark', '正在处理...')
                results = task_data.get("results", [])
                
                # --- 优化点: 主动检查完成状态 ---
                # 如果进度为100%且结果URL已存在，或状态为completed，都视为完成
                is_completed = False
                video_url = None
                if results and results[0].get("result_url"):
                    video_url = results[0]["result_url"]
                    if progress == 100 or status == "completed":
                        is_completed = True

                if is_completed:
                    logger.success(f"任务 {task_id} 完成，获取到结果 URL。")
                    final_data = {"status": "completed", "url": video_url}
                    yield f"data: {json.dumps(final_data)}\n\n"
                    return # 结束生成器

                if status == "failed":
                    error_msg = task_data.get("task_remark", "未知错误")
                    raise Exception(f"上游任务处理失败: {error_msg}")

                # 如果未完成，则发送进度更新
                event_data = {
                    "status": "processing",
                    "progress": progress,
                    "remark": remark
                }
                yield f"data: {json.dumps(event_data)}\n\n"
            
            raise Exception("轮询任务状态超时。")

        except Exception as e:
            logger.error(f"处理视频流任务 {task_id} 时出错: {e}", exc_info=True)
            error_data = {"status": "failed", "error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
        finally:
            logger.info(f"任务 {task_id} 的流式传输结束。")
            yield "data: [DONE]\n\n"

    async def _generate_video_blocking(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        阻塞版本的实现，供 chat_completions 调用。
        """
        try:
            task_info = await self.submit_video_task(request_data)
            task_id = task_info["task_id"]
            
            async for event_str in self.stream_task_progress(task_id):
                if event_str.strip() == "data: [DONE]":
                    break
                
                data_str = event_str[6:].strip()
                if not data_str:
                    continue
                
                try:
                    data = json.loads(data_str)
                    if data.get("status") == "completed":
                        return {
                            "created": int(time.time()),
                            "data": [{"url": data["url"]}]
                        }
                    elif data.get("status") == "failed":
                        raise Exception(data.get("error", "未知失败原因"))
                except (json.JSONDecodeError, KeyError):
                    continue

            raise Exception("轮询结束但未收到 'completed' 或 'failed' 状态。")

        except Exception as e:
            logger.error(f"处理阻塞式视频任务时出错: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")

    async def get_models(self) -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": name, "object": "model", "created": int(time.time()), "owned_by": "lzA6"}
                for name in settings.MODEL_MAPPING.keys()
            ]
        }

    # BaseProvider 抽象方法的实现
    async def generate_video(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        # 修复了之前版本中的无限递归bug
        return await self._generate_video_blocking(request_data)
