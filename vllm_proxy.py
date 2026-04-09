#!/usr/bin/env python3
"""
vLLM API 代理服务 - OpenClaw 对接
将本地 vLLM 服务暴露给 OpenClaw 使用
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn
import os

VLLM_URL = os.getenv("VLLM_URL", "http://127.0.0.1:8000")
PORT = int(os.getenv("PORT", "8001"))
VLLM_MODEL = "/models/Qwen3-32B-AWQ"

app = FastAPI(title="vLLM Proxy for OpenClaw")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/models")
async def list_models():
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(f"{VLLM_URL}/v1/models")
        return JSONResponse(content=response.json())

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    
    stream = body.get("stream", False)
    auth_header = request.headers.get("Authorization", "")
    
    model_name = body.get("model", "")
    if model_name.startswith("openai-compatible:"):
        model_name = model_name.replace("openai-compatible:", "")
    if "openai-compatible/" in model_name:
        model_name = model_name.split("openai-compatible/")[-1]
    if "openai-compatible:" in model_name:
        model_name = model_name.split("openai-compatible:")[-1]
    
    if not model_name.startswith("/models/"):
        if not model_name.startswith("/"):
            model_name = "/models/" + model_name
        else:
            model_name = "/models" + model_name
    
    body["model"] = model_name if model_name else VLLM_MODEL
    
    max_tokens = min(body.get("max_tokens", 1024), 2048)
    body["max_tokens"] = max_tokens
    if "chat_template_kwargs" not in body:
        body["chat_template_kwargs"] = {}
    body["chat_template_kwargs"]["enable_thinking"] = False
    
    messages = body.get("messages", [])
    messages = messages[-5:] if len(messages) > 5 else messages
    body["messages"] = messages
    
    if "tools" in body:
        del body["tools"]
    if "tool_choice" in body:
        del body["tool_choice"]
    
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        if stream:
            response = await client.post(
                f"{VLLM_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            )
            
            if response.status_code != 200:
                return JSONResponse(content=response.json(), status_code=response.status_code)
            
            async def generate():
                async for line in response.aiter_lines():
                    if line.strip():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                        elif line == "data: [DONE]":
                            yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        
        response = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json=body,
            headers=headers
        )
        
        if response.status_code != 200:
            return JSONResponse(content=response.json(), status_code=response.status_code)
        
        return JSONResponse(content=response.json())

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    body["model"] = VLLM_MODEL
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{VLLM_URL}/v1/completions",
            json=body,
            headers={"Content-Type": "application/json"}
        )
        return JSONResponse(content=response.json())

@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    
    stream = body.get("stream", False)
    auth_header = request.headers.get("Authorization", "")
    
    model_name = body.get("model", "")
    if model_name.startswith("openai-compatible:"):
        model_name = model_name.replace("openai-compatible:", "")
    if "openai-compatible/" in model_name:
        model_name = model_name.split("openai-compatible/")[-1]
    if "openai-compatible:" in model_name:
        model_name = model_name.split("openai-compatible:")[-1]
    
    if not model_name.startswith("/models/"):
        if not model_name.startswith("/"):
            model_name = "/models/" + model_name
        else:
            model_name = "/models" + model_name
    
    messages_data = body.get("messages", [])
    converted_messages = []
    for msg in messages_data:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
            content = " ".join(text_parts)
        if len(content) > 200:
            content = content[:200] + "..."
        converted_messages.append({"role": role, "content": content})
    
    if not converted_messages:
        converted_messages = [{"role": "user", "content": "hello"}]
    if converted_messages[-1].get("role") != "user":
        converted_messages.append({"role": "user", "content": "hello"})
    
    converted_messages = converted_messages[-2:] if len(converted_messages) > 2 else converted_messages
    
    max_tokens = min(body.get("max_tokens", 1024), 2048)
    
    payload = {
        "model": model_name,
        "messages": converted_messages,
        "max_tokens": max_tokens,
        "temperature": body.get("temperature", 0.7),
    }
    
    if "chat_template_kwargs" not in payload:
        payload["chat_template_kwargs"] = {}
    payload["chat_template_kwargs"]["enable_thinking"] = False
    
    if "tools" in payload:
        del payload["tools"]
    
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        if stream:
            response = await client.post(
                f"{VLLM_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            
            if response.status_code != 200:
                return JSONResponse(content=response.json(), status_code=response.status_code)
            
            async def generate():
                async for line in response.aiter_lines():
                    if line.strip():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                        elif line == "data: [DONE]":
                            yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        
        response = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json=payload,
            headers=headers
        )
        
        if response.status_code != 200:
            return JSONResponse(content=response.json(), status_code=response.status_code)
        
        result = response.json()
        assistant_msg = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return JSONResponse(content={
            "id": "msg-" + str(int(1000)),
            "object": "chat.completion",
            "created": 0,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_msg
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        })

if __name__ == "__main__":
    print(f"vLLM 代理服务启动中...")
    print(f"  vLLM 地址: {VLLM_URL}")
    print(f"  监听端口: {PORT}")
    print()
    print(f"OpenClaw 配置:")
    print(f"  API 地址: http://<你的IP>:{PORT}")
    print(f"  模型: /models/Qwen3-32B-AWQ")
    print()
    uvicorn.run(app, host="0.0.0.0", port=PORT)
