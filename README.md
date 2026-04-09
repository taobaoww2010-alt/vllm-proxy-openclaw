# vLLM Proxy for OpenClaw

将本地 vLLM 大模型服务暴露给 OpenClaw 使用的代理服务。

## 硬件配置

- **CPU**: 44 核心
- **内存**: 23GB
- **GPU**: AMD Radeon RX 7900 XTX (24GB VRAM) × 2
- **系统**: Ubuntu 22.04

## 软件环境

- Python 3.10+
- vLLM (ROCm 6.3)
- Docker
- FastAPI + httpx

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn httpx
```

### 2. 配置 vLLM 模型路径

确保你的模型在 `/models/` 目录下，或者修改 `vllm_proxy.py` 中的 `VLLM_MODEL` 变量。

### 3. 启动 vLLM 服务

```bash
# 使用 Docker 启动 vLLM
docker run -d --name vllm-server \
  --restart unless-stopped \
  --network=host \
  --ipc=host \
  --shm-size=16g \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add video \
  -v /path/to/models:/models \
  nalanzeyu/vllm-gfx906:v0.9.0-rocm6.3 \
  vllm serve /models/Qwen3-32B-AWQ \
  --tensor-parallel-size 2 \
  --quantization awq \
  --max-model-len 5100 \
  --dtype float16
```

### 4. 启动代理服务

```bash
# 方式一：直接运行
cd /home/tomlee/vllm-proxy-openclaw
python3 vllm_proxy.py

# 方式二：使用 systemd 服务
sudo cp vllm_proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vllm_proxy
sudo systemctl start vllm_proxy
```

### 5. OpenClaw 配置

在 OpenClaw 中配置：

- **API 地址**: `http://<你的电脑IP>:8001/v1`
- **模型 ID**: `/models/Qwen3-32B-AWQ`
- **API 类型**: `openai-completions`
- **API Key**: 任意值 (如 `sk-any`)
- **maxTokens**: 建议 512-2048

## 配置参数

可以通过环境变量配置：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VLLM_URL` | `http://127.0.0.1:8000` | vLLM 服务地址 |
| `PORT` | `8001` | 代理服务端口 |

## 注意事项

1. **Token 限制**: 模型最大支持 5100 tokens，已自动限制 `max_tokens` 为 2048
2. **消息截断**: OpenClaw 发送的消息可能包含很长的 system prompt，已自动截断和过滤
3. **Tools 参数**: 已自动移除 `tools` 参数避免 token 超限

## 故障排除

### 查看日志

```bash
# systemd 日志
journalctl -u vllm_proxy -f

# vLLM 日志
docker logs vllm-server -f
```

### 测试 API

```bash
# 健康检查
curl http://localhost:8001/health

# 模型列表
curl http://localhost:8001/v1/models

# 测试聊天
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 100
  }'
```

## 许可

MIT License
