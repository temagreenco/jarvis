"""
AI Providers - Multi-provider abstraction for LLM APIs
Supports: OpenAI, Google Gemini, Anthropic Claude
"""
from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import json
import asyncio

from utils.logger import get_logger

logger = get_logger("ai_providers")


class ProviderType(Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    OLLAMA = "ollama"  # Local fallback


@dataclass
class AIResponse:
    """Standardized response from any AI provider"""
    content: str
    provider: ProviderType
    model: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AIMessage:
    """Chat message format"""
    role: str  # "system", "user", "assistant"
    content: str


class BaseAIProvider(ABC):
    """Abstract base for all AI providers"""

    provider_type: ProviderType
    default_model: str

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.default_model
        self.logger = get_logger(f"ai.{self.provider_type.value}")
        self._client = None

    @abstractmethod
    async def generate(
        self,
        messages: list[AIMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False
    ) -> AIResponse:
        """Generate a response from the AI"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available"""
        pass

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD - override per provider"""
        return 0.0


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT provider"""

    provider_type = ProviderType.OPENAI
    default_model = "gpt-4o"

    # Pricing per 1M tokens (as of 2024)
    PRICING = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    }

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        messages: list[AIMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False
    ) -> AIResponse:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        if not self._client:
            self._client = AsyncOpenAI(api_key=self.api_key)

        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        self.logger.debug(f"Calling OpenAI {self.model}...")
        response = await self._client.chat.completions.create(**kwargs)

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        return AIResponse(
            content=response.choices[0].message.content,
            provider=self.provider_type,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=self._calculate_cost(input_tokens, output_tokens),
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens}
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING.get(self.model, self.PRICING["gpt-4o"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost


class GeminiProvider(BaseAIProvider):
    """Google Gemini provider"""

    provider_type = ProviderType.GEMINI
    default_model = "gemini-1.5-pro"

    PRICING = {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
    }

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        messages: list[AIMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False
    ) -> AIResponse:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)

        # Convert messages to Gemini format
        # Gemini uses 'user' and 'model' roles
        history = []
        system_prompt = ""

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                history.append({"role": "user", "parts": [msg.content]})
            elif msg.role == "assistant":
                history.append({"role": "model", "parts": [msg.content]})

        # Prepend system to first user message if exists
        if system_prompt and history:
            history[0]["parts"][0] = f"{system_prompt}\n\n{history[0]['parts'][0]}"

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        self.logger.debug(f"Calling Gemini {self.model}...")

        # Run synchronous API in executor
        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        last_message = history[-1]["parts"][0] if history else ""

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: chat.send_message(last_message, generation_config=generation_config)
        )

        # Estimate tokens (Gemini doesn't always return exact counts)
        input_tokens = sum(len(m.content.split()) * 1.3 for m in messages)
        output_tokens = len(response.text.split()) * 1.3

        return AIResponse(
            content=response.text,
            provider=self.provider_type,
            model=self.model,
            tokens_used=int(input_tokens + output_tokens),
            cost_usd=self._calculate_cost(int(input_tokens), int(output_tokens)),
            metadata={"estimated_tokens": True}
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING.get(self.model, self.PRICING["gemini-1.5-pro"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost


class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude provider"""

    provider_type = ProviderType.CLAUDE
    default_model = "claude-sonnet-4-20250514"

    PRICING = {
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        messages: list[AIMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False
    ) -> AIResponse:
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        if not self._client:
            self._client = AsyncAnthropic(api_key=self.api_key)

        # Extract system message
        system_prompt = None
        formatted_messages = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                formatted_messages.append({"role": msg.role, "content": msg.content})

        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        self.logger.debug(f"Calling Claude {self.model}...")
        response = await self._client.messages.create(**kwargs)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return AIResponse(
            content=response.content[0].text,
            provider=self.provider_type,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=self._calculate_cost(input_tokens, output_tokens),
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens}
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING.get(self.model, self.PRICING["claude-sonnet-4-20250514"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost


class OllamaProvider(BaseAIProvider):
    """Local Ollama provider (fallback)"""

    provider_type = ProviderType.OLLAMA
    default_model = "llama3.1:8b"

    def __init__(self, host: str = "http://localhost:11434", model: Optional[str] = None):
        self.host = host
        self.model = model or self.default_model
        self.api_key = ""  # Not needed for local
        self.logger = get_logger("ai.ollama")

    def is_available(self) -> bool:
        try:
            import httpx
            response = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            return response.status_code == 200
        except:
            return False

    async def generate(
        self,
        messages: list[AIMessage],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False
    ) -> AIResponse:
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx package not installed. Run: pip install httpx")

        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        if json_mode:
            payload["format"] = "json"

        self.logger.debug(f"Calling Ollama {self.model}...")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()
            data = response.json()

        return AIResponse(
            content=data["message"]["content"],
            provider=self.provider_type,
            model=self.model,
            tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            cost_usd=0.0,  # Free local
            metadata={"eval_duration": data.get("eval_duration")}
        )


class AIProviderManager:
    """
    Manages multiple AI providers with fallback support.

    Usage:
        manager = AIProviderManager()
        manager.add_provider(OpenAIProvider(api_key="..."))
        manager.add_provider(ClaudeProvider(api_key="..."))

        response = await manager.generate(messages, preferred_provider=ProviderType.OPENAI)
    """

    def __init__(self):
        self.providers: dict[ProviderType, BaseAIProvider] = {}
        self.logger = get_logger("ai.manager")
        self.fallback_order = [
            ProviderType.OPENAI,
            ProviderType.CLAUDE,
            ProviderType.GEMINI,
            ProviderType.OLLAMA
        ]

    def add_provider(self, provider: BaseAIProvider) -> None:
        """Add a provider to the manager"""
        self.providers[provider.provider_type] = provider
        self.logger.info(f"Added provider: {provider.provider_type.value} ({provider.model})")

    def get_provider(self, provider_type: ProviderType) -> Optional[BaseAIProvider]:
        """Get a specific provider"""
        return self.providers.get(provider_type)

    def get_available_providers(self) -> list[ProviderType]:
        """Get list of available providers"""
        return [p for p, provider in self.providers.items() if provider.is_available()]

    async def generate(
        self,
        messages: list[AIMessage],
        preferred_provider: Optional[ProviderType] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False,
        fallback: bool = True
    ) -> AIResponse:
        """
        Generate response using preferred provider with fallback.

        Args:
            messages: List of chat messages
            preferred_provider: Preferred provider to use
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            json_mode: Request JSON response format
            fallback: Enable fallback to other providers on failure
        """
        providers_to_try = []

        # Add preferred provider first
        if preferred_provider and preferred_provider in self.providers:
            providers_to_try.append(preferred_provider)

        # Add fallback providers
        if fallback:
            for p in self.fallback_order:
                if p not in providers_to_try and p in self.providers:
                    providers_to_try.append(p)

        if not providers_to_try:
            raise ValueError("No AI providers configured!")

        last_error = None

        for provider_type in providers_to_try:
            provider = self.providers[provider_type]

            if not provider.is_available():
                self.logger.warning(f"Provider {provider_type.value} not available, skipping...")
                continue

            try:
                self.logger.info(f"Using provider: {provider_type.value}")
                return await provider.generate(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode
                )
            except Exception as e:
                last_error = e
                self.logger.error(f"Provider {provider_type.value} failed: {e}")
                if not fallback:
                    raise

        raise RuntimeError(f"All providers failed. Last error: {last_error}")


# Convenience function to create manager from settings
def create_ai_manager_from_settings(settings) -> AIProviderManager:
    """Create AIProviderManager from JARVIS settings"""
    manager = AIProviderManager()

    if settings.openai_api_key:
        manager.add_provider(OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        ))

    if settings.gemini_api_key:
        manager.add_provider(GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model
        ))

    if settings.claude_api_key:
        manager.add_provider(ClaudeProvider(
            api_key=settings.claude_api_key,
            model=settings.claude_model
        ))

    # Always add Ollama as local fallback
    manager.add_provider(OllamaProvider(
        host=settings.ollama_host,
        model=settings.ollama_model
    ))

    return manager
