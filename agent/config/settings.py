"""
Agent Configuration Settings
============================

IMPORTANT CONCEPTS:

1. Pydantic Settings:
   - Automatically loads from environment variables
   - Prefix: AGENT_ (e.g., AGENT_LLM_MODEL="llama3.1:70b")
   - Type validation ensures correct values

2. Why These Settings Matter:
   - LLM settings: Control which model powers your agent's "brain"
   - Tool settings: Enable/disable capabilities, set safety limits
   - RunPod settings: Configure for cloud GPU deployment

3. Environment Variables Override:
   You can override ANY setting via environment variables:

   export AGENT_LLM_MODEL="qwen2.5:72b"
   export AGENT_LLM_PROVIDER="vllm"
   export AGENT_MAX_ITERATIONS=50
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Literal
from pathlib import Path


class LLMSettings(BaseSettings):
    """
    LLM (Large Language Model) Configuration

    This controls the "brain" of your agent - which AI model it uses.

    PROVIDER OPTIONS:
    - "ollama": Easy to set up, good for development
    - "vllm": Faster inference, better for production
    - "openai": Use OpenAI API (or compatible endpoints)

    MODEL RECOMMENDATIONS (for RunPod):
    - A100 40GB: llama3.1:8b, qwen2.5:7b (small but fast)
    - A100 80GB: llama3.1:70b, qwen2.5:72b (powerful)
    - H100: Any model, fastest inference
    """

    provider: Literal["ollama", "vllm", "openai"] = Field(
        default="ollama",
        description="Which LLM backend to use"
    )

    model: str = Field(
        default="llama3.1:8b",
        description="Model name/ID to use"
    )

    # Where to reach the LLM server
    base_url: str = Field(
        default="http://localhost:11434",  # Ollama default
        description="LLM API endpoint URL"
    )

    api_key: str = Field(
        default="",
        description="API key (if required by provider)"
    )

    # Generation parameters
    temperature: float = Field(
        default=0.7,
        ge=0.0, le=2.0,
        description="Creativity (0=deterministic, 1=creative, 2=chaotic)"
    )

    max_tokens: int = Field(
        default=4096,
        description="Max response length in tokens"
    )

    # Context window - how much the agent can "remember" in one conversation
    context_window: int = Field(
        default=32768,
        description="Max context length (depends on model)"
    )

    model_config = {"env_prefix": "AGENT_LLM_"}


class ToolSettings(BaseSettings):
    """
    Tool/Capability Configuration

    SECURITY CONCEPT:
    Tools let the agent DO things (run code, access files, etc.)
    These settings control WHAT the agent is allowed to do.

    SAFETY LIMITS:
    - sandbox_enabled: Run code in isolated environment
    - allowed_paths: Restrict file access to specific directories
    - max_execution_time: Prevent infinite loops
    """

    # Code execution
    code_execution_enabled: bool = Field(
        default=True,
        description="Allow agent to run Python/JS code"
    )

    sandbox_enabled: bool = Field(
        default=True,
        description="Run code in sandbox (IMPORTANT for security)"
    )

    max_execution_time: int = Field(
        default=30,
        description="Max seconds for code/command execution"
    )

    # File system access
    file_access_enabled: bool = Field(
        default=True,
        description="Allow agent to read/write files"
    )

    allowed_paths: list[str] = Field(
        default=["/home/user/jarvis", "/tmp", "/workspace", "/app"],
        description="Directories agent can access (includes /workspace for Docker)"
    )

    # Shell commands
    shell_enabled: bool = Field(
        default=True,
        description="Allow agent to run bash commands"
    )

    dangerous_commands_blocked: list[str] = Field(
        default=["rm -rf /", "mkfs", ":(){:|:&};:", "dd if=/dev/zero"],
        description="Commands that are NEVER allowed"
    )

    # Web access
    web_enabled: bool = Field(
        default=True,
        description="Allow agent to fetch URLs"
    )

    model_config = {"env_prefix": "AGENT_TOOL_"}


class AgentSettings(BaseSettings):
    """
    Core Agent Behavior Configuration

    KEY CONCEPTS:

    1. max_iterations:
       The ReAct loop (Think→Act→Observe) repeats until task is done.
       This prevents infinite loops if agent gets stuck.

    2. memory_enabled:
       Long-term memory using embeddings (vectors).
       Agent can remember past conversations/learnings.

    3. verbose:
       Shows agent's thinking process (great for debugging).
    """

    name: str = Field(
        default="JARVIS",
        description="Agent's name"
    )

    # ReAct loop control
    max_iterations: int = Field(
        default=25,
        ge=1, le=100,
        description="Max Think→Act→Observe cycles before stopping"
    )

    # Memory
    memory_enabled: bool = Field(
        default=True,
        description="Enable long-term memory (vector store)"
    )

    conversation_history_limit: int = Field(
        default=50,
        description="How many messages to keep in context"
    )

    # Debugging
    verbose: bool = Field(
        default=True,
        description="Show detailed agent reasoning"
    )

    # Working directory
    workspace: Path = Field(
        default=Path("/home/user/jarvis"),
        description="Agent's working directory"
    )

    model_config = {"env_prefix": "AGENT_"}


class RunPodSettings(BaseSettings):
    """
    RunPod-Specific Configuration

    RUNPOD CONCEPTS:

    1. Pod Types:
       - GPU Pod: Has GPU (A100, H100, etc.) - for running LLM
       - CPU Pod: No GPU - for simple tasks

    2. Serverless vs Pod:
       - Serverless: Pay per request, auto-scales, cold starts
       - Pod: Always-on, predictable cost, no cold starts

    3. Network Volume:
       Persistent storage that survives pod restarts.
       Store your models here to avoid re-downloading.
    """

    # Pod configuration
    gpu_type: str = Field(
        default="NVIDIA A100 80GB",
        description="GPU type for RunPod"
    )

    gpu_count: int = Field(
        default=1,
        description="Number of GPUs (2 for 70B models with tensor parallelism)"
    )

    # Storage
    network_volume_path: Path = Field(
        default=Path("/runpod-volume"),
        description="Path to RunPod network volume (persistent storage)"
    )

    model_cache_path: Path = Field(
        default=Path("/runpod-volume/models"),
        description="Where to cache downloaded models"
    )

    # Networking
    expose_port: int = Field(
        default=8000,
        description="Port to expose agent API"
    )

    model_config = {"env_prefix": "RUNPOD_"}


class Settings(BaseSettings):
    """
    Master Settings - Combines All Configuration

    HOW TO USE:

    1. Import the singleton:
       from config import settings

    2. Access nested settings:
       settings.llm.model
       settings.tools.sandbox_enabled
       settings.agent.max_iterations

    3. Override via environment:
       export AGENT_LLM_MODEL="qwen2.5:72b"
       export AGENT_MAX_ITERATIONS=50
    """

    llm: LLMSettings = Field(default_factory=LLMSettings)
    tools: ToolSettings = Field(default_factory=ToolSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    runpod: RunPodSettings = Field(default_factory=RunPodSettings)

    model_config = {"env_prefix": "AGENT_"}


# Singleton instance - import this in other files
settings = Settings()
