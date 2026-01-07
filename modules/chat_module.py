"""
Chat Module - Conversational AI interface for JARVIS

Features:
- Natural language conversation with Ollama LLM
- Conversation context/memory management
- Multi-interface support (CLI, Telegram, API)
- System prompt customization
- Streaming response support
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("chat")


def check_ollama_available() -> tuple[bool, str]:
    """Check if Ollama service is available"""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.ollama_host}/api/tags")
            response.raise_for_status()
            return True, "Ollama is available"
    except httpx.ConnectError:
        return False, f"Cannot connect to Ollama at {settings.ollama_host}"
    except Exception as e:
        return False, f"Ollama check failed: {e}"


@dataclass
class Message:
    """A single chat message"""
    role: str  # 'user', 'assistant', or 'system'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Conversation:
    """A conversation session with history"""
    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation"""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        return msg

    def get_context(self, max_messages: int = 20) -> list[dict]:
        """Get recent messages formatted for LLM"""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m.role, "content": m.content} for m in recent]

    def clear(self) -> None:
        """Clear conversation history"""
        self.messages = []


class ConversationStore:
    """Persistent storage for conversations"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / "data" / "conversations.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.conversations: dict[str, Conversation] = {}
        self._load()

    def _load(self) -> None:
        """Load conversations from disk"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for conv_id, conv_data in data.items():
                        messages = [Message(**m) for m in conv_data.get("messages", [])]
                        self.conversations[conv_id] = Conversation(
                            id=conv_id,
                            messages=messages,
                            created_at=conv_data.get("created_at", datetime.now().isoformat()),
                            metadata=conv_data.get("metadata", {})
                        )
                logger.debug(f"Loaded {len(self.conversations)} conversations")
            except Exception as e:
                logger.warning(f"Failed to load conversations: {e}")
                self.conversations = {}

    def _save(self) -> None:
        """Save conversations to disk"""
        try:
            data = {}
            for conv_id, conv in self.conversations.items():
                data[conv_id] = {
                    "id": conv.id,
                    "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in conv.messages],
                    "created_at": conv.created_at,
                    "metadata": conv.metadata
                }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save conversations: {e}")

    def get_or_create(self, conversation_id: str) -> Conversation:
        """Get existing or create new conversation"""
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = Conversation(id=conversation_id)
            self._save()
        return self.conversations[conversation_id]

    def save(self, conversation: Conversation) -> None:
        """Save a conversation"""
        self.conversations[conversation.id] = conversation
        self._save()

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            self._save()
            return True
        return False

    def list_conversations(self, limit: int = 10) -> list[Conversation]:
        """List recent conversations"""
        sorted_convs = sorted(
            self.conversations.values(),
            key=lambda c: c.created_at,
            reverse=True
        )
        return sorted_convs[:limit]


class ChatModule(BaseModule):
    """
    Conversational AI module for JARVIS.
    Handles natural language chat via Ollama LLM.
    """

    name = "chat"
    description = "Natural language conversation with AI assistant"
    version = "0.1.0"

    # Keywords that indicate chat task
    TASK_KEYWORDS = [
        "chat", "talk", "ask", "tell", "say", "respond", "answer",
        "question", "help", "explain", "describe", "what", "how", "why",
        "message", "conversation"
    ]

    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant. You are:
- Helpful, knowledgeable, and efficient
- Direct and concise in your responses
- Capable of handling a wide variety of tasks
- Proactive in offering solutions

When you don't know something, admit it honestly. When you can help, do so thoroughly."""

    def __init__(self):
        super().__init__()
        self.store = ConversationStore()
        self.system_prompt = getattr(settings, 'chat_system_prompt', None) or self.DEFAULT_SYSTEM_PROMPT

    def is_available(self) -> tuple[bool, str]:
        """Check if chat service is available"""
        return check_ollama_available()

    def can_handle(self, task: str) -> bool:
        """Check if this is a chat/conversation task"""
        task_lower = task.lower()
        # Chat module can handle most natural language queries
        return any(kw in task_lower for kw in self.TASK_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate chat inputs"""
        message = kwargs.get("message")
        if not message:
            return False, "message is required"
        return True, None

    def _call_ollama(
        self,
        messages: list[dict],
        stream: bool = False
    ) -> str | Generator[str, None, None]:
        """Call Ollama API for chat completion"""
        url = f"{settings.ollama_host}/api/chat"

        # Add system prompt if not present
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": self.system_prompt}] + messages

        model = getattr(settings, 'chat_model', None) or settings.ollama_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": getattr(settings, 'chat_temperature', 0.7),
                "num_predict": getattr(settings, 'chat_max_tokens', 2048),
            }
        }

        if stream:
            return self._stream_response(url, payload)
        else:
            return self._sync_response(url, payload)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True
    )
    def _sync_response(self, url: str, payload: dict) -> str:
        """Get synchronous response from Ollama with retry logic"""
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            raise RuntimeError("Chat request timed out. Please try again.")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise RuntimeError(f"Chat service error: {e.response.status_code}")
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {settings.ollama_host}")
            raise RuntimeError(f"Cannot connect to Ollama. Is it running at {settings.ollama_host}?")
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise RuntimeError(f"Failed to get response: {e}")

    def _stream_response(self, url: str, payload: dict) -> Generator[str, None, None]:
        """Stream response from Ollama"""
        try:
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if data.get("done"):
                                break
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise RuntimeError(f"Streaming failed: {e}")

    def execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute a chat request.

        Args:
            task: The task description (used for routing)
            message: The user's message to respond to
            conversation_id: Optional conversation ID for context
            stream: Whether to stream the response
            system_prompt: Optional custom system prompt

        Returns:
            TaskResult with the assistant's response
        """
        message = kwargs.get("message", task)
        conversation_id = kwargs.get("conversation_id", "default")
        stream = kwargs.get("stream", False)
        custom_system_prompt = kwargs.get("system_prompt")

        # Get or create conversation
        conversation = self.store.get_or_create(conversation_id)

        # Add user message
        conversation.add_message("user", message)

        # Get conversation context
        context = conversation.get_context(max_messages=getattr(settings, 'chat_context_messages', 20))

        # Override system prompt if provided
        if custom_system_prompt:
            context = [{"role": "system", "content": custom_system_prompt}] + [
                m for m in context if m["role"] != "system"
            ]

        try:
            # Get response from LLM
            if stream:
                # For streaming, return generator in metadata
                response_gen = self._call_ollama(context, stream=True)
                full_response = ""
                for chunk in response_gen:
                    full_response += chunk
                response = full_response
            else:
                response = self._call_ollama(context, stream=False)

            # Add assistant response to conversation
            conversation.add_message("assistant", response)
            self.store.save(conversation)

            return TaskResult(
                success=True,
                data={
                    "response": response,
                    "conversation_id": conversation_id,
                    "message_count": len(conversation.messages)
                },
                metadata={
                    "model": getattr(settings, 'chat_model', None) or settings.ollama_model,
                    "conversation_id": conversation_id
                }
            )

        except Exception as e:
            logger.error(f"Chat execution failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"conversation_id": conversation_id}
            )

    def new_conversation(self, conversation_id: Optional[str] = None) -> str:
        """Start a new conversation"""
        import uuid
        conv_id = conversation_id or str(uuid.uuid4())[:8]
        self.store.get_or_create(conv_id)
        logger.info(f"Created new conversation: {conv_id}")
        return conv_id

    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation's history"""
        conv = self.store.get_or_create(conversation_id)
        conv.clear()
        self.store.save(conv)
        return True

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation entirely"""
        return self.store.delete(conversation_id)

    def list_conversations(self, limit: int = 10) -> list[dict]:
        """List recent conversations"""
        convs = self.store.list_conversations(limit)
        return [
            {
                "id": c.id,
                "created_at": c.created_at,
                "message_count": len(c.messages),
                "last_message": c.messages[-1].content[:100] if c.messages else None
            }
            for c in convs
        ]
