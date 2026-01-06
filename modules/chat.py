"""
Chat Module - Conversational AI for JARVIS
Handles user conversations with memory and context.
"""
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger


@dataclass
class ChatMessage:
    """A single message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


@dataclass
class Conversation:
    """A conversation with message history"""
    conversation_id: str
    user_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    system_prompt: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> ChatMessage:
        """Add a message to the conversation"""
        msg = ChatMessage(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now()
        return msg

    def get_context_messages(self, max_messages: int = 20) -> list[dict]:
        """Get messages formatted for LLM context"""
        context = []
        if self.system_prompt:
            context.append({"role": "system", "content": self.system_prompt})

        # Get last N messages for context window
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        for msg in recent:
            context.append({"role": msg.role, "content": msg.content})

        return context

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "messages": [m.to_dict() for m in self.messages],
            "system_prompt": self.system_prompt,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(
            conversation_id=data["conversation_id"],
            user_id=data["user_id"],
            messages=[ChatMessage.from_dict(m) for m in data.get("messages", [])],
            system_prompt=data.get("system_prompt", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )


class ConversationStore:
    """Persistent storage for conversations"""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (settings.base_dir / "data" / "conversations")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Conversation] = {}
        self.logger = get_logger("chat.store")

    def _get_path(self, conversation_id: str) -> Path:
        return self.storage_dir / f"{conversation_id}.json"

    def save(self, conversation: Conversation) -> None:
        """Save conversation to disk"""
        path = self._get_path(conversation.conversation_id)
        with open(path, "w") as f:
            json.dump(conversation.to_dict(), f, indent=2)
        self._cache[conversation.conversation_id] = conversation

    def load(self, conversation_id: str) -> Optional[Conversation]:
        """Load conversation from disk"""
        if conversation_id in self._cache:
            return self._cache[conversation_id]

        path = self._get_path(conversation_id)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
            conversation = Conversation.from_dict(data)
            self._cache[conversation_id] = conversation
            return conversation
        except Exception as e:
            self.logger.error(f"Failed to load conversation {conversation_id}: {e}")
            return None

    def get_or_create(self, conversation_id: str, user_id: str, system_prompt: str = "") -> Conversation:
        """Get existing conversation or create new one"""
        conversation = self.load(conversation_id)
        if conversation is None:
            conversation = Conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                system_prompt=system_prompt
            )
            self.save(conversation)
        return conversation

    def list_user_conversations(self, user_id: str) -> list[str]:
        """List all conversation IDs for a user"""
        conversations = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if data.get("user_id") == user_id:
                    conversations.append(data["conversation_id"])
            except Exception:
                continue
        return conversations


class ChatModule(BaseModule):
    """
    Chat Module - Conversational AI capabilities for JARVIS

    Provides intelligent conversation with:
    - Multi-turn dialogue with context
    - Persistent conversation history
    - Configurable system prompts
    - Integration with Ollama LLM
    """

    name = "chat"
    description = "Conversational AI with persistent memory"
    version = "0.1.0"

    # Keywords that trigger this module
    TRIGGER_KEYWORDS = [
        "chat", "talk", "message", "conversation", "ask", "tell",
        "speak", "discuss", "help", "question", "say"
    ]

    DEFAULT_SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant. You are helpful, knowledgeable, and efficient.
Your responses should be:
- Clear and concise
- Accurate and informative
- Friendly but professional
- Action-oriented when tasks are involved

If you don't know something, say so. If you need clarification, ask one clear question."""

    def __init__(self):
        super().__init__()
        self.store = ConversationStore()
        self._ollama = None

    def _get_ollama(self):
        """Lazy load ollama client"""
        if self._ollama is None:
            try:
                import ollama
                self._ollama = ollama
            except ImportError:
                raise RuntimeError("ollama not installed. Run: pip install ollama")
        return self._ollama

    def can_handle(self, task: str) -> bool:
        """Check if this module should handle the task"""
        task_lower = task.lower()
        return any(keyword in task_lower for keyword in self.TRIGGER_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate chat inputs"""
        message = kwargs.get("message")
        if not message and not kwargs.get("task_is_message", False):
            # If no explicit message, the task itself might be the message
            return True, None
        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute a chat interaction"""
        # Extract parameters
        message = kwargs.get("message", task)  # Use task as message if not provided
        user_id = kwargs.get("user_id", "default")
        conversation_id = kwargs.get("conversation_id", f"{user_id}_default")
        system_prompt = kwargs.get("system_prompt", self.DEFAULT_SYSTEM_PROMPT)
        new_conversation = kwargs.get("new_conversation", False)

        try:
            # Get or create conversation
            if new_conversation:
                conversation_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            conversation = self.store.get_or_create(
                conversation_id=conversation_id,
                user_id=user_id,
                system_prompt=system_prompt
            )

            # Add user message
            conversation.add_message("user", message)

            # Get LLM response
            response = self._generate_response(conversation)

            # Add assistant response
            conversation.add_message("assistant", response)

            # Save conversation
            self.store.save(conversation)

            self.logger.info(f"Chat completed for user {user_id}, conversation {conversation_id}")

            return TaskResult(
                success=True,
                data={
                    "response": response,
                    "conversation_id": conversation_id,
                    "message_count": len(conversation.messages)
                },
                metadata={
                    "user_id": user_id,
                    "model": settings.ollama_model
                }
            )

        except Exception as e:
            self.logger.error(f"Chat failed: {e}")
            return TaskResult(
                success=False,
                error=str(e)
            )

    def _generate_response(self, conversation: Conversation) -> str:
        """Generate a response using Ollama"""
        ollama = self._get_ollama()

        messages = conversation.get_context_messages(
            max_messages=settings.chat_context_messages
        )

        response = ollama.chat(
            model=settings.ollama_model,
            messages=messages
        )

        return response["message"]["content"]

    def get_conversation_history(self, conversation_id: str) -> Optional[list[dict]]:
        """Get the message history for a conversation"""
        conversation = self.store.load(conversation_id)
        if conversation:
            return [m.to_dict() for m in conversation.messages]
        return None

    def list_conversations(self, user_id: str) -> list[str]:
        """List all conversations for a user"""
        return self.store.list_user_conversations(user_id)

    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation's history (start fresh)"""
        conversation = self.store.load(conversation_id)
        if conversation:
            conversation.messages = []
            conversation.updated_at = datetime.now()
            self.store.save(conversation)
            return True
        return False
