# JARVIS Agent - Autonomous AI Assistant

An agentic AI system designed to run on RunPod GPU servers.

## Architecture Overview

```
agent/
├── config/           # Settings & environment configuration
│   └── settings.py   # Pydantic settings (LLM, tools, RunPod)
├── core/             # Brain of the agent
│   ├── agent.py      # Main orchestrator (like Claude's brain)
│   ├── reasoning.py  # ReAct loop (Think → Act → Observe)
│   └── llm.py        # LLM client (vLLM/Ollama)
├── tools/            # Capabilities (what the agent CAN DO)
│   ├── base.py       # Base class all tools inherit from
│   ├── code_executor.py    # Run Python/JS code safely
│   ├── file_ops.py         # Read/write/search files
│   ├── shell.py            # Execute bash commands
│   └── web.py              # Fetch URLs, search web
├── memory/           # Persistence layer
│   ├── conversation.py     # Chat history
│   └── vector_store.py     # Long-term memory (embeddings)
├── prompts/          # System prompts & templates
│   └── system.py     # Core system prompt
└── main.py           # Entry point
```

## Key Concepts

### 1. ReAct Pattern (Reasoning + Acting)
The agent follows a loop:
1. **Think** - Analyze the task, plan approach
2. **Act** - Call a tool (file read, code run, etc.)
3. **Observe** - See the result
4. **Repeat** until task complete

### 2. Tools
Tools are capabilities. Each tool:
- Has a `name` and `description` (LLM reads these to decide what to use)
- Has `parameters` schema (what inputs it needs)
- Has an `execute()` method (does the actual work)

### 3. LLM Backend
On RunPod, you'll run an open-source LLM:
- **Recommended**: Llama 3.1 70B or Qwen 2.5 72B
- **Served via**: vLLM (fast) or Ollama (simple)
- **Hardware**: A100 80GB or H100 for 70B models

## Quick Start

```bash
# 1. Create virtual environment
cd /home/user/jarvis/agent
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up LLM (choose one):
# Option A: Ollama (simple)
ollama serve &
ollama pull llama3.1:70b

# Option B: vLLM (fast, production)
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --tensor-parallel-size 2

# 4. Run the agent
python main.py
```

## RunPod Deployment
See `RUNPOD_SETUP.md` for detailed deployment instructions.
