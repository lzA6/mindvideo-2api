# /main.py
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.providers.mindvideo_provider import MindVideoProvider

# --- 配置 Loguru ---
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True
)

# --- 全局 Provider 实例 ---
provider = MindVideoProvider()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"应用启动中... {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("服务已进入 'Dynamic Signature & Polling' 模式。")
    logger.info(f"API 服务将在 http://localhost:{settings.NGINX_PORT} 上可用")
    logger.info(f"Web UI 测试界面已启用，请访问 http://localhost:{settings.NGINX_PORT}/")
    yield
    logger.info("应用关闭。")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan
)

# --- 添加 CORS 中间件 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 挂载静态文件目录 ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 安全依赖 ---
async def verify_api_key(authorization: Optional[str] = Header(None)):
    if settings.API_MASTER_KEY and settings.API_MASTER_KEY != "1":
        if not authorization or "bearer" not in authorization.lower():
            raise HTTPException(status_code=401, detail="需要 Bearer Token 认证。")
        token = authorization.split(" ")[-1]
        if token != settings.API_MASTER_KEY:
            raise HTTPException(status_code=403, detail="无效的 API Key。")

# --- API 路由 ---
@app.post("/v1/images/generations", dependencies=[Depends(verify_api_key)])
async def create_image_generation_task(request: Request):
    """
    接收视频生成请求，提交任务并立即返回 task_id。
    """
    try:
        request_data = await request.json()
        task_info = await provider.submit_video_task(request_data)
        return JSONResponse(content=task_info)
    except Exception as e:
        logger.error(f"提交视频生成任务时发生顶层错误: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

@app.get("/v1/tasks/{task_id}/stream", dependencies=[Depends(verify_api_key)])
async def stream_image_generation_progress(task_id: int):
    """
    使用 Server-Sent Events (SSE) 流式传输任务进度。
    """
    return StreamingResponse(
        provider.stream_task_progress(task_id),
        media_type="text/event-stream"
    )

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request):
    try:
        request_data = await request.json()
        
        messages = request_data.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="请求体中缺少 'messages' 字段。")
        
        last_user_message = next((m['content'] for m in reversed(messages) if m.get('role') == 'user'), None)
        if not last_user_message:
            raise HTTPException(status_code=400, detail="在 'messages' 中未找到用户消息。")

        model_name = request_data.get("model", settings.DEFAULT_MODEL)
        
        video_request_data = {
            "prompt": last_user_message,
            "model": model_name,
            "n": 1,
            "size": "720x1280", # 聊天接口默认使用竖屏
            "response_format": "url"
        }
        
        logger.info(f"通过聊天接口适配视频生成 (阻塞模式)，使用模型 '{model_name}' 和 prompt: '{last_user_message[:50]}...'")
        video_result_dict = await provider.generate_video(video_request_data)

        if not video_result_dict.get("data") or not video_result_dict["data"][0].get("url"):
            raise HTTPException(status_code=502, detail="从上游服务生成视频失败。")
            
        video_url = video_result_dict["data"][0]["url"]
        response_content = f"视频已生成：点击查看 <sup>1</sup> [<sup>1</sup>]({video_url})"
        
        chat_response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_content,
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        }
        
        return JSONResponse(content=chat_response)

    except Exception as e:
        logger.error(f"处理聊天生成请求时发生顶层错误: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    model_data = await provider.get_models()
    return JSONResponse(content=model_data)

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="UI 文件 (static/index.html) 未找到。")
