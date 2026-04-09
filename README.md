# 双卡 Radeon VII / MI50 使用张量并行运行大语言模型

## 硬件配置

- **GPU**: AMD MI50 16GB × 2 (架构: gfx906)
- **CPU**: 44 核心
- **内存**: 23GB
- **系统**: Ubuntu 22.04

> 注: 本项目同样适用于双卡 Radeon VII 显卡

---

## 第一部分：系统底层环境配置

### 1. BIOS/UEFI 设置

进入 BIOS/UEFI 设置界面，进行以下两项关键修改：

- **启用 "Above 4G Decoding"**: 允许 64 位操作系统正确映射多个 GPU 所需的巨大内存地址空间
- **禁用 "Compatibility Support Module (CSM)"**: 强制系统进入纯 UEFI 启动模式

### 2. 安装 Docker Engine

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker
```

---

## 第二部分：ROCm 驱动与验证

### 1. 安装 ROCm 6.3

```bash
wget https://repo.radeon.com/amdgpu-install/6.3/ubuntu/jammy/amdgpu-install_6.3.60300-1_all.deb
sudo apt install ./amdgpu-install_6.3.60300-1_all.deb
sudo amdgpu-install -y --usecase=rocm,hiplibsdk
```

### 2. 配置用户权限

```bash
sudo usermod -a -G render,video $LOGNAME
sudo reboot
```

### 3. 验证 ROCm 环境

```bash
groups  # 应包含 render 和 video
dkms status  # 应显示 amdgpu 已安装
rocminfo  # 应显示 2 个 Agent，Name 为 gfx906
rocm-smi  # 应显示 2 张显卡，每张 16384MiB
```

---

## 第三部分：使用 vLLM-GFX906 部署模型

### 1. 拉取 Docker 镜像

```bash
docker pull nalanzeyu/vllm-gfx906:v0.9.0-rocm6.3
```

### 2. 启动 vLLM 服务器

```bash
docker run -d --name vllm-server \
  --restart unless-stopped \
  --network=host \
  --ipc=host \
  --shm-size=16g \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add video \
  -v /path/to/your/models:/models \
  nalanzeyu/vllm-gfx906:v0.9.0-rocm6.3 \
  vllm serve /models/Qwen3-32B-AWQ \
  --tensor-parallel-size 2 \
  --quantization awq \
  --max-model-len 5100 \
  --disable-log-requests \
  --dtype float16
```

**参数说明**:
- `--tensor-parallel-size 2`: 将模型分片到 2 张 GPU
- `--quantization awq`: 指定 AWQ 量化格式
- `--max-model-len 5100`: 最大序列长度

---

## 第四部分：OpenClaw 对接配置

### 1. 安装代理服务依赖

```bash
pip install fastapi uvicorn httpx
```

### 2. 配置模型路径

```bash
sudo ln -sf /home/tomlee/models /models
```

### 3. 启动代理服务

**方式一：直接运行**
```bash
cd /home/tomlee/vllm-proxy-openclaw
python3 vllm_proxy.py
```

**方式二：使用 systemd (推荐)**
```bash
sudo cp vllm_proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vllm_proxy
sudo systemctl start vllm_proxy
```

**开机自启**: 服务已配置 `Restart=always`，重启服务器后自动运行

### 4. OpenClaw 配置

- **API 地址**: `http://<你的IP>:8001/v1`
- **模型 ID**: `/models/Qwen3-32B-AWQ`
- **API 类型**: `openai-completions`
- **API Key**: 任意值 (如 `sk-any`)
- **maxTokens**: 建议 512-2048

---

## 代理服务配置参数

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VLLM_URL` | `http://127.0.0.1:8000` | vLLM 服务地址 |
| `PORT` | `8001` | 代理服务端口 |

---

## API 接口说明

### 1. /health 健康检查

```bash
curl http://localhost:8001/health
```

返回: `{"status": "ok"}`

### 2. /v1/models 模型列表

```bash
curl http://localhost:8001/v1/models
```

### 3. /v1/chat/completions 聊天接口

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 512
  }'
```

### 4. /v1/messages 消息接口 (OpenClaw 专用)

```bash
curl -X POST http://localhost:8001/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

---

## 第五部分：测试

### 测试 vLLM

```bash
curl http://localhost:8000/v1/models
```

### 测试代理

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 100
  }'
```

### 查看日志

```bash
# 代理日志
journalctl -u vllm_proxy -f

# vLLM 日志
docker logs vllm-server -f
```

---

## 故障排除

### Token 超限

如果遇到 `HTTP 400: token limit exceeded` 错误：
- 在 OpenClaw 中降低 maxTokens 值
- 代理已自动限制 max_tokens 为 2048

### 查看 GPU 状态

```bash
rocm-smi
```

---

## 项目地址

- **vLLM 部署教程**: https://gitee.com/spoto/R7vllm
- **OpenClaw 代理**: https://github.com/taobaoww2010-alt/vllm-proxy-openclaw

---

# Dual Radeon VII / MI50 with Tensor Parallel LLM Deployment

## Hardware

- **GPU**: AMD MI50 16GB × 2 (arch: gfx906)
- **CPU**: 44 cores
- **Memory**: 23GB
- **OS**: Ubuntu 22.04

---

## Part 1: System Setup

### 1. BIOS/UEFI Settings

- Enable **"Above 4G Decoding"**
- Disable **"Compatibility Support Module (CSM)"**

### 2. Install Docker

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker
```

---

## Part 2: ROCm Driver

### 1. Install ROCm 6.3

```bash
wget https://repo.radeon.com/amdgpu-install/6.3/ubuntu/jammy/amdgpu-install_6.3.60300-1_all.deb
sudo apt install ./amdgpu-install_6.3.60300-1_all.deb
sudo amdgpu-install -y --usecase=rocm,hiplibsdk
```

### 2. Configure User Permissions

```bash
sudo usermod -a -G render,video $LOGNAME
sudo reboot
```

### 3. Verify ROCm

```bash
groups  # should contain render and video
dkms status  # should show amdgpu installed
rocminfo  # should show 2 agents with Name gfx906
rocm-smi  # should show 2 GPUs, each 16384MiB
```

---

## Part 3: Deploy vLLM Model

### 1. Pull Docker Image

```bash
docker pull nalanzeyu/vllm-gfx906:v0.9.0-rocm6.3
```

### 2. Start vLLM Server

```bash
docker run -d --name vllm-server \
  --restart unless-stopped \
  --network=host \
  --ipc=host \
  --shm-size=16g \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add video \
  -v /path/to/your/models:/models \
  nalanzeyu/vllm-gfx906:v0.9.0-rocm6.3 \
  vllm serve /models/Qwen3-32B-AWQ \
  --tensor-parallel-size 2 \
  --quantization awq \
  --max-model-len 5100 \
  --disable-log-requests \
  --dtype float16
```

---

## Part 4: OpenClaw Integration

### 1. Install Dependencies

```bash
pip install fastapi uvicorn httpx
```

### 2. Configure Model Path

```bash
sudo ln -sf /home/tomlee/models /models
```

### 3. Start Proxy Service

**Option 1: Direct Run**
```bash
cd /home/tomlee/vllm-proxy-openclaw
python3 vllm_proxy.py
```

**Option 2: Systemd (Recommended)**
```bash
sudo cp vllm_proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vllm_proxy
sudo systemctl start vllm_proxy
```

**Auto-start on boot**: Service is configured with `Restart=always`, will auto-run after server reboot

### 4. OpenClaw Configuration

- **API URL**: `http://<your-ip>:8001/v1`
- **Model ID**: `/models/Qwen3-32B-AWQ`
- **API Type**: `openai-completions`
- **API Key**: Any value (e.g., `sk-any`)
- **maxTokens**: 512-2048 recommended

---

## Proxy Service Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `VLLM_URL` | `http://127.0.0.1:8000` | vLLM server address |
| `PORT` | `8001` | Proxy service port |

---

## API Endpoints

### 1. /health Health Check

```bash
curl http://localhost:8001/health
```

Returns: `{"status": "ok"}`

### 2. /v1/models Model List

```bash
curl http://localhost:8001/v1/models
```

### 3. /v1/chat/completions Chat API

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 512
  }'
```

### 4. /v1/messages Messages API (OpenClaw)

```bash
curl -X POST http://localhost:8001/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## Part 5: Testing

### Test vLLM

```bash
curl http://localhost:8000/v1/models
```

### Test Proxy

```bash
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B-AWQ",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

### View Logs

```bash
# Proxy logs
journalctl -u vllm_proxy -f

# vLLM logs
docker logs vllm-server -f
```

---

## Troubleshooting

### Token Limit Exceeded

If you get `HTTP 400: token limit exceeded`:
- Lower maxTokens in OpenClaw
- Proxy already limits max_tokens to 2048

### Check GPU Status

```bash
rocm-smi
```

---

## References

- **vLLM Deployment Guide**: https://gitee.com/spoto/R7vllm
- **OpenClaw Proxy**: https://github.com/taobaoww2010-alt/vllm-proxy-openclaw
