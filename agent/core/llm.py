"""
LLM Client
==========

Handles communication with the language model backend.

SUPPORTED BACKENDS:
-------------------
1. OLLAMA (default):
   - Easy to set up: `ollama serve && ollama pull llama3.1:8b`
   - Good for development
   - API: http://localhost:11434/api/chat

2. vLLM:
   - Faster inference (continuous batching)
   - Better for production
   - OpenAI-compatible API
   - Start: `python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-3.1-70B-Instruct`

3. OpenAI-compatible:
   - Works with any OpenAI API compatible service
   - Together.ai, Groq, local servers, etc.

WHY ABSTRACT THE LLM?
---------------------
By having a unified interface, we can:
- Switch backends without changing agent code
- Test with small models, deploy with large ones
- Use different providers (local vs cloud)

MESSAGE FORMAT:
---------------
All LLMs use a chat format with roles:
- system: Instructions for how the AI should behave
- user: What the human says
- assistant: What the AI says
- tool: Results from tool execution (some APIs)

TOOL CALLING:
-------------
Modern LLMs support "function calling" / "tool use":
1. We tell the LLM what tools are available (JSON schemas)
2. LLM decides which tool to use and with what parameters
3. We execute the tool and send result back
4. LLM continues reasoning
"""

import json
import aiohttp
from typing import AsyncGenerator
from dataclasses import dataclass

from config import settings


@dataclass
class Message:
    """
    A single message in the conversation.

    ROLES:
    - system: Instructions (usually first message)
    - user: Human input
    - assistant: AI response
    - tool: Tool execution result

    WHY DATACLASS?
    -------------
    Simple, typed structure that's easy to:
    - Create: Message(role="user", content="Hello")
    - Serialize: Convert to dict for API calls
    - Debug: Clear repr showing all fields
    """
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[dict] | None = None  # For assistant messages with tool calls
    tool_call_id: str | None = None  # For tool result messages

    def to_dict(self) -> dict:
        """Convert to dict for API calls."""
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class ToolCall:
    """
    Represents an LLM's decision to use a tool.

    EXAMPLE:
    When LLM wants to read a file, it outputs:
    {
        "id": "call_123",
        "name": "read_file",
        "arguments": {"file_path": "/home/user/test.py"}
    }

    We parse this into a ToolCall object for easier handling.
    """
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """
    Response from the LLM.

    FIELDS:
    - content: Text response (if any)
    - tool_calls: Tools the LLM wants to use (if any)
    - finish_reason: Why generation stopped
        - "stop": Natural end
        - "tool_calls": Wants to use tools
        - "length": Hit token limit
    """
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str


class LLMClient:
    """
    Client for communicating with LLM backends.

    USAGE:
    ------
    client = LLMClient()

    # Simple completion
    response = await client.chat([
        Message(role="user", content="Hello!")
    ])

    # With tools
    response = await client.chat(messages, tools=tool_schemas)
    if response.tool_calls:
        # Execute the tools...

    PROVIDER DIFFERENCES:
    ---------------------
    Each provider has slightly different APIs. This class
    abstracts those differences so agent code stays clean.
    """

    def __init__(self):
        self.provider = settings.llm.provider
        self.model = settings.llm.model
        self.base_url = settings.llm.base_url
        self.api_key = settings.llm.api_key
        self.temperature = settings.llm.temperature
        self.max_tokens = settings.llm.max_tokens

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None
    ) -> LLMResponse:
        """
        Send messages to LLM and get response.

        PARAMETERS:
        -----------
        messages: Conversation history
        tools: Available tools (JSON schemas)
        temperature: Override default temperature
        max_tokens: Override default max tokens

        RETURNS:
        --------
        LLMResponse with content and/or tool_calls
        """
        if self.provider == "ollama":
            return await self._chat_ollama(messages, tools, temperature, max_tokens)
        elif self.provider in ("vllm", "openai"):
            return await self._chat_openai_compatible(messages, tools, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _chat_ollama(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        temperature: float | None,
        max_tokens: int | None
    ) -> LLMResponse:
        """
        Chat using Ollama API.

        OLLAMA API:
        -----------
        POST http://localhost:11434/api/chat
        {
            "model": "llama3.1:8b",
            "messages": [...],
            "tools": [...],  # Optional
            "stream": false
        }

        TOOL SUPPORT:
        Ollama supports tools natively since v0.3.0
        """
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": max_tokens or self.max_tokens
            }
        }

        if tools:
            # Convert our tool format to Ollama format
            payload["tools"] = self._convert_tools_for_ollama(tools)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Ollama API error: {resp.status} - {error_text}")

                data = await resp.json()

        # Parse response
        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = []

        # Check for tool calls in Ollama format
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{len(tool_calls)}"),
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"]
                ))

        finish_reason = "tool_calls" if tool_calls else "stop"

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason
        )

    async def _chat_openai_compatible(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        temperature: float | None,
        max_tokens: int | None
    ) -> LLMResponse:
        """
        Chat using OpenAI-compatible API (vLLM, Together, Groq, etc.)

        OPENAI API FORMAT:
        ------------------
        POST /v1/chat/completions
        {
            "model": "...",
            "messages": [...],
            "tools": [...],
            "temperature": 0.7,
            "max_tokens": 4096
        }

        WHY OPENAI-COMPATIBLE?
        ----------------------
        Many providers use this format:
        - vLLM (local deployment)
        - Together.ai (cloud)
        - Groq (fast inference)
        - Fireworks.ai
        - OpenRouter

        By supporting this, we support MANY backends.
        """
        url = f"{self.base_url}/v1/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens
        }

        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error: {resp.status} - {error_text}")

                data = await resp.json()

        # Parse response
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content")
        tool_calls = []

        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                # Arguments might be string (needs parsing) or dict
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)

                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=args
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop")
        )

    def _convert_tools_for_ollama(self, tools: list[dict]) -> list[dict]:
        """
        Convert tool schemas to Ollama format.

        Ollama expects:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        """
        return [{"type": "function", "function": tool} for tool in tools]

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream response tokens (for real-time output).

        STREAMING:
        ----------
        Instead of waiting for full response, get tokens as they're generated.
        Better UX for long responses - user sees progress.

        YIELD:
        Each yield is a chunk of text (could be word, part of word, etc.)
        """
        if self.provider == "ollama":
            async for chunk in self._stream_ollama(messages, tools):
                yield chunk
        else:
            async for chunk in self._stream_openai_compatible(messages, tools):
                yield chunk

    async def _stream_ollama(
        self,
        messages: list[Message],
        tools: list[dict] | None
    ) -> AsyncGenerator[str, None]:
        """Stream from Ollama API."""
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }

        if tools:
            payload["tools"] = self._convert_tools_for_ollama(tools)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                async for line in resp.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            continue

    async def _stream_openai_compatible(
        self,
        messages: list[Message],
        tools: list[dict] | None
    ) -> AsyncGenerator[str, None]:
        """Stream from OpenAI-compatible API."""
        url = f"{self.base_url}/v1/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError):
                            continue
