#!/bin/bash
# ============================================
# JARVIS Agent - RunPod Setup Script
# ============================================
#
# RUN THIS ON YOUR RUNPOD POD:
#   chmod +x setup_runpod.sh
#   ./setup_runpod.sh
#
# WHAT IT DOES:
# 1. Creates virtual environment
# 2. Installs dependencies
# 3. Installs Ollama
# 4. Pulls a small LLM model
# 5. Starts the agent

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║           JARVIS Agent - RunPod Setup                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Create virtual environment
echo -e "${YELLOW}[1/5] Creating virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created .venv"
else
    echo ".venv already exists"
fi

# Activate venv
source .venv/bin/activate

# Step 2: Install dependencies
echo -e "${YELLOW}[2/5] Installing Python dependencies...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "Dependencies installed"

# Step 3: Install Ollama
echo -e "${YELLOW}[3/5] Installing Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "Ollama installed"
else
    echo "Ollama already installed"
fi

# Step 4: Start Ollama and pull model
echo -e "${YELLOW}[4/5] Starting Ollama and pulling model...${NC}"

# Start Ollama in background if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 3
    echo "Ollama server started"
else
    echo "Ollama already running"
fi

# Check GPU and pull appropriate model
if nvidia-smi &> /dev/null; then
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    echo "GPU detected with ${GPU_MEM}MB memory"

    if [ "$GPU_MEM" -gt 40000 ]; then
        MODEL="llama3.1:8b"
        echo "Using llama3.1:8b (good for 40GB+ GPU)"
    else
        MODEL="llama3.2:3b"
        echo "Using llama3.2:3b (for smaller GPUs)"
    fi
else
    MODEL="llama3.2:3b"
    echo "No GPU detected, using llama3.2:3b (CPU mode)"
fi

# Pull model if not exists
if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling $MODEL (this may take a few minutes)..."
    ollama pull "$MODEL"
else
    echo "Model $MODEL already available"
fi

# Step 5: Create run script
echo -e "${YELLOW}[5/5] Creating run script...${NC}"

cat > run_agent.sh << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
source .venv/bin/activate

# Make sure Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 2
fi

# Set environment
export AGENT_LLM_PROVIDER=ollama
export AGENT_LLM_MODEL=$MODEL
export AGENT_LLM_BASE_URL=http://localhost:11434

# Run agent
python main.py
EOF
chmod +x run_agent.sh

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "To run the agent:"
echo "  ./run_agent.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
