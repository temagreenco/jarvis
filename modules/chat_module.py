"""
Chat Module - Conversational AI capabilities for JARVIS
Uses Ollama for local LLM inference.
"""
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("chat")


@dataclass
class Message:
    """A single message in a conversation"""
    role: str  # "user", "assistant", or "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**data)


@dataclass
class Conversation:
    """A conversation with message history"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    title: Optional[str] = None

    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation"""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()

        # Auto-generate title from first user message
        if self.title is None and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")

        return msg

    def get_context(self, max_messages: int = 10) -> list[dict]:
        """Get recent messages for LLM context"""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m.role, "content": m.content} for m in recent]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            messages=messages,
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            title=data.get("title")
        )

    def clear(self) -> None:
        """Clear all messages"""
        self.messages = []
        self.updated_at = datetime.now().isoformat()


class ConversationStore:
    """Persistent storage for conversations"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or settings.chat_data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "conversations.json"
        self._conversations: dict[str, Conversation] = {}
        self._load()

    def _load(self) -> None:
        """Load conversations from file"""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                    for conv_data in data.get("conversations", []):
                        conv = Conversation.from_dict(conv_data)
                        self._conversations[conv.id] = conv
                logger.debug(f"Loaded {len(self._conversations)} conversations")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load conversations: {e}")
                self._conversations = {}

    def _save(self) -> None:
        """Save conversations to file"""
        data = {
            "conversations": [conv.to_dict() for conv in self._conversations.values()]
        }
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=2)

    def create(self) -> Conversation:
        """Create a new conversation"""
        conv = Conversation()
        self._conversations[conv.id] = conv
        self._save()
        return conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID"""
        return self._conversations.get(conversation_id)

    def get_or_create(self, conversation_id: Optional[str] = None) -> Conversation:
        """Get existing or create new conversation"""
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]
        return self.create()

    def save(self, conversation: Conversation) -> None:
        """Save a conversation"""
        self._conversations[conversation.id] = conversation
        self._save()

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            self._save()
            return True
        return False

    def list_recent(self, limit: int = 10) -> list[Conversation]:
        """List recent conversations"""
        sorted_convs = sorted(
            self._conversations.values(),
            key=lambda c: c.updated_at,
            reverse=True
        )
        return sorted_convs[:limit]


class ChatModule(BaseModule):
    """
    Chat module for conversational AI.
    Uses Ollama for local LLM inference.
    """

    name = "chat"
    description = "Conversational AI using local LLM"
    version = "0.1.0"

    TASK_KEYWORDS = ["chat", "talk", "ask", "question", "conversation", "discuss"]

    def __init__(self):
        super().__init__()
        self.store = ConversationStore()
        self.current_conversation: Optional[Conversation] = None
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client"""
        if self._client is None:
            self._client = httpx.Client(
                base_url=settings.ollama_host,
                timeout=settings.chat_timeout
            )
        return self._client

    def can_handle(self, task: str) -> bool:
        """Check if this task is a chat request"""
        task_lower = task.lower()
        return any(keyword in task_lower for keyword in self.TASK_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate chat inputs"""
        message = kwargs.get("message")
        if message is not None and not isinstance(message, str):
            return False, "Message must be a string"
        return True, None

    def check_ollama_health(self) -> bool:
        """Check if Ollama service is available"""
        try:
            response = self.client.get("/api/tags")
            return response.status_code == 200
        except httpx.RequestError as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException))
    )
    def _call_ollama(self, messages: list[dict]) -> str:
        """Call Ollama API with retry logic"""
        # Add system prompt at the beginning
        full_messages = [
            {"role": "system", "content": settings.chat_system_prompt}
        ] + messages

        response = self.client.post(
            "/api/chat",
            json={
                "model": settings.chat_model,
                "messages": full_messages,
                "stream": False
            }
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None
    ) -> tuple[str, Conversation]:
        """
        Send a message and get a response.

        Args:
            message: The user's message
            conversation_id: Optional conversation ID to continue

        Returns:
            Tuple of (response_text, conversation)
        """
        # Get or create conversation
        conversation = self.store.get_or_create(conversation_id)
        self.current_conversation = conversation

        # Add user message
        conversation.add_message("user", message)

        # Get context for LLM
        context = conversation.get_context(settings.chat_context_length)

        # Call Ollama
        try:
            response_text = self._call_ollama(context)
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            # Remove the user message on failure
            if conversation.messages and conversation.messages[-1].role == "user":
                conversation.messages.pop()
            raise

        # Add assistant response
        conversation.add_message("assistant", response_text)

        # Save conversation
        self.store.save(conversation)

        return response_text, conversation

    def stream_chat(
        self,
        message: str,
        conversation_id: Optional[str] = None
    ) -> Generator[str, None, Conversation]:
        """
        Stream a chat response token by token.

        Args:
            message: The user's message
            conversation_id: Optional conversation ID to continue

        Yields:
            Response tokens as they arrive

        Returns:
            The conversation object (accessible after iteration)
        """
        # Get or create conversation
        conversation = self.store.get_or_create(conversation_id)
        self.current_conversation = conversation

        # Add user message
        conversation.add_message("user", message)

        # Get context for LLM
        context = conversation.get_context(settings.chat_context_length)

        # Add system prompt
        full_messages = [
            {"role": "system", "content": settings.chat_system_prompt}
        ] + context

        # Stream from Ollama
        full_response = []
        try:
            with self.client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": settings.chat_model,
                    "messages": full_messages,
                    "stream": True
                }
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            full_response.append(token)
                            yield token
        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            # Remove the user message on failure
            if conversation.messages and conversation.messages[-1].role == "user":
                conversation.messages.pop()
            raise

        # Add assistant response
        response_text = "".join(full_response)
        conversation.add_message("assistant", response_text)

        # Save conversation
        self.store.save(conversation)

        return conversation

    def new_conversation(self) -> Conversation:
        """Start a new conversation"""
        conversation = self.store.create()
        self.current_conversation = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a specific conversation"""
        return self.store.get(conversation_id)

    def list_conversations(self, limit: int = 10) -> list[Conversation]:
        """List recent conversations"""
        return self.store.list_recent(limit)

    def clear_conversation(self, conversation_id: Optional[str] = None) -> bool:
        """Clear messages from a conversation"""
        conv_id = conversation_id or (self.current_conversation.id if self.current_conversation else None)
        if conv_id:
            conv = self.store.get(conv_id)
            if conv:
                conv.clear()
                self.store.save(conv)
                return True
        return False

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute a chat task"""
        message = kwargs.get("message", task)
        conversation_id = kwargs.get("conversation_id")

        # Check Ollama availability
        if not self.check_ollama_health():
            return TaskResult(
                success=False,
                error="Ollama service is not available. Please ensure Ollama is running."
            )

        try:
            response, conversation = self.chat(message, conversation_id)
            return TaskResult(
                success=True,
                data=response,
                metadata={
                    "conversation_id": conversation.id,
                    "message_count": len(conversation.messages)
                }
            )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e)
            )

    def __del__(self):
        """Cleanup HTTP client"""
        if self._client:
            self._client.close()
