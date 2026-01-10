# JARVIS Agent - Docker Setup
# ============================
#
# WHY DOCKER?
# -----------
# 1. Consistent environment - works the same everywhere
# 2. Easy dependency management - no "it works on my machine"
# 3. Isolation - agent can't mess up your system
# 4. Mirrors RunPod - test locally before deploying
#
# HOW IT WORKS:
# -------------
# We use TWO containers:
# 1. ollama - Runs the LLM (Llama, Qwen, etc.)
# 2. agent  - Runs JARVIS agent (connects to Ollama)
#
# They communicate over a Docker network.

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc: For compiling Python packages
# - git: For cloning repos (if agent needs it)
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker cache optimization)
# If requirements don't change, this layer is cached
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Create a non-root user for security
# Running as root in containers is bad practice
RUN useradd -m -u 1000 jarvis && \
    chown -R jarvis:jarvis /app

# Create workspace directory
RUN mkdir -p /workspace && chown jarvis:jarvis /workspace

# Switch to non-root user
USER jarvis

# Set environment variables
# These can be overridden at runtime
ENV AGENT_LLM_PROVIDER=ollama
ENV AGENT_LLM_MODEL=llama3.2:3b
ENV AGENT_LLM_BASE_URL=http://ollama:11434
ENV AGENT_WORKSPACE=/workspace
ENV PYTHONUNBUFFERED=1

# Default command - interactive mode
CMD ["python", "main.py"]
