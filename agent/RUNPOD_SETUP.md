# RunPod Deployment Guide

Complete guide to deploying JARVIS Agent on RunPod.

## What is RunPod?

RunPod is a cloud GPU platform where you can rent powerful GPUs (A100, H100) for AI workloads. It's perfect for running large language models like Llama 70B.

**Pricing** (as of 2024):
- A100 40GB: ~$0.79/hr
- A100 80GB: ~$1.19/hr (recommended for 70B models)
- H100 80GB: ~$3.99/hr (fastest)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      RunPod GPU Pod                         │
│                                                             │
│  ┌─────────────┐       ┌──────────────────────────────┐    │
│  │   JARVIS    │       │         LLM Server           │    │
│  │   Agent     │ ───▶  │    (Ollama or vLLM)          │    │
│  │  (Python)   │       │    Llama 3.1 70B             │    │
│  └─────────────┘       └──────────────────────────────┘    │
│        │                           │                        │
│        │                           │                        │
│        ▼                           ▼                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Network Volume (persistent)             │   │
│  │   /runpod-volume/models/  ← Cached model files      │   │
│  │   /runpod-volume/data/    ← Agent workspace         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Step 1: Create RunPod Account

1. Go to https://runpod.io
2. Sign up and add credits ($10-50 to start)
3. Add SSH key (Settings → SSH Keys) for pod access

## Step 2: Create a Network Volume

**WHY**: Network volumes persist data when pods restart. Store your models here to avoid re-downloading (70B model is ~40GB!).

1. Go to **Storage** → **Network Volumes**
2. Click **+ New Network Volume**
3. Settings:
   - Name: `jarvis-volume`
   - Size: 100GB (enough for 2-3 large models)
   - Region: Choose closest to you

## Step 3: Create a GPU Pod

1. Go to **Pods** → **+ New Pod**
2. Choose GPU:
   - **A100 80GB PCIe** - Best for 70B models
   - **A100 40GB** - Good for 8B-13B models
3. Select template: **RunPod Pytorch 2.0** or **Ollama**
4. Configure:
   - Container disk: 50GB
   - Volume: Attach your `jarvis-volume` to `/runpod-volume`
   - Expose ports: 8000 (for agent API), 11434 (for Ollama)
5. Deploy!

## Step 4: Connect to Your Pod

### Option A: Web Terminal
Click "Connect" → "Web Terminal" on your pod

### Option B: SSH (recommended)
```bash
# Get SSH command from pod details
ssh root@YOUR_POD_IP -p YOUR_PORT -i ~/.ssh/your_key
```

## Step 5: Set Up LLM Backend

### Option A: Ollama (Simple, Recommended for Getting Started)

```bash
# Install Ollama (may already be installed)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve &

# Pull a model (choose based on your GPU)
# For A100 80GB - can run 70B models:
ollama pull llama3.1:70b

# For A100 40GB - use smaller models:
ollama pull llama3.1:8b
ollama pull qwen2.5:7b

# Test it works
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.1:8b",
  "messages": [{"role": "user", "content": "Hello!"}],
  "stream": false
}'
```

### Option B: vLLM (Faster, For Production)

```bash
# Install vLLM
pip install vllm

# Serve model (adjust based on GPU count)
# Single A100 80GB:
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9

# Two A100s (for 70B):
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --tensor-parallel-size 2 \
  --max-model-len 32768

# Cache models on network volume (faster restarts):
export HF_HOME=/runpod-volume/huggingface
```

## Step 6: Set Up JARVIS Agent

```bash
# Clone your repo (or copy files)
cd /runpod-volume
git clone https://github.com/YOUR_USERNAME/jarvis.git
cd jarvis/agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure for your LLM
export AGENT_LLM_PROVIDER="ollama"  # or "vllm"
export AGENT_LLM_MODEL="llama3.1:8b"
export AGENT_LLM_BASE_URL="http://localhost:11434"  # Ollama
# export AGENT_LLM_BASE_URL="http://localhost:8000/v1"  # vLLM

# Run the agent
python main.py
```

## Step 7: Save Your Setup (Persist Across Restarts)

Create a startup script:

```bash
cat > /runpod-volume/start_jarvis.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting JARVIS setup..."

# Start Ollama if using it
if command -v ollama &> /dev/null; then
    echo "Starting Ollama..."
    ollama serve &
    sleep 5  # Wait for Ollama to start
fi

# Activate environment
cd /runpod-volume/jarvis/agent
source .venv/bin/activate

# Set environment
export AGENT_LLM_PROVIDER="ollama"
export AGENT_LLM_MODEL="llama3.1:8b"
export AGENT_LLM_BASE_URL="http://localhost:11434"

echo "Starting JARVIS Agent..."
python main.py
EOF

chmod +x /runpod-volume/start_jarvis.sh
```

Now when pod restarts: `/runpod-volume/start_jarvis.sh`

## Recommended Models by GPU

| GPU | VRAM | Recommended Models |
|-----|------|-------------------|
| RTX 4090 | 24GB | llama3.1:8b, qwen2.5:7b |
| A100 40GB | 40GB | llama3.1:8b, qwen2.5:14b, mixtral:8x7b |
| A100 80GB | 80GB | llama3.1:70b, qwen2.5:72b |
| H100 80GB | 80GB | llama3.1:70b (fastest), deepseek-v3 |

## Cost Optimization Tips

### 1. Use Spot Instances
RunPod offers "Community Cloud" (spot instances) at 50%+ discount. Good for development, but pods can be interrupted.

### 2. Stop When Not Using
Pods charge per hour. Stop your pod when done:
- RunPod console → Pod → Stop

### 3. Use Network Volume
Models don't need to redownload when pod restarts.

### 4. Right-Size Your GPU
- Development: A100 40GB with 8B model
- Production: A100 80GB with 70B model

## Exposing Your Agent as API (Optional)

Want to access your agent from outside RunPod? Add an API server:

```python
# api_server.py
from fastapi import FastAPI
from pydantic import BaseModel
import asyncio

from core.agent import Agent

app = FastAPI()
agent = Agent(verbose=False)

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    response = await agent.chat(request.message)
    return ChatResponse(response=response)

# Run with: uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Then expose port 8000 in RunPod and access via:
```bash
curl https://YOUR_POD_ID-8000.proxy.runpod.net/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

## Troubleshooting

### "Connection refused" to LLM
```bash
# Check if Ollama is running
pgrep -f ollama
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve &
```

### "Out of memory"
- Use a smaller model
- Reduce context length: `--max-model-len 16384`
- Use quantized model: `ollama pull llama3.1:70b-q4_0`

### Model download slow
```bash
# Use network volume for cache
export HF_HOME=/runpod-volume/huggingface
export OLLAMA_MODELS=/runpod-volume/ollama/models
```

### Pod keeps restarting
- Check logs in RunPod console
- Reduce GPU memory usage
- Check disk space: `df -h`

## Next Steps

1. **Add more tools**: Extend `/agent/tools/` with custom capabilities
2. **Add memory**: Implement vector store in `/agent/memory/`
3. **Build UI**: Create web interface with Gradio or Streamlit
4. **Deploy serverless**: Use RunPod Serverless for pay-per-request

Good luck with your AI! 🚀
