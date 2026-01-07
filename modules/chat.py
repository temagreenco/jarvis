"""
Chat Module - Conversational AI interface for JARVIS
Handles natural language conversations using Ollama.
"""
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
from pathlib import Path

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


@dataclass
class Message:
    """A single message in a conversation"""
    role: str  # "user", "assistant", or "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Conversation:
    """A conversation with message history"""
    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation"""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()
        return msg

    def get_context(self, max_messages: int = 20) -> list[dict]:
        """Get conversation context for LLM"""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m.role, "content": m.content} for m in recent]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "messages": [asdict(m) for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Create from dictionary"""
        messages = [Message(**m) for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            messages=messages,
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


class ConversationMemory:
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
                    for conv_data in data:
                        conv = Conversation.from_dict(conv_data)
                        self.conversations[conv.id] = conv
            except Exception:
                self.conversations = {}

    def _save(self) -> None:
        """Save conversations to disk"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump([c.to_dict() for c in self.conversations.values()], f, indent=2)
        except Exception:
            pass

    def get_or_create(self, conversation_id: str = "default") -> Conversation:
        """Get existing conversation or create new one"""
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = Conversation(id=conversation_id)
            self._save()
        return self.conversations[conversation_id]

    def save_conversation(self, conversation: Conversation) -> None:
        """Save a conversation"""
        self.conversations[conversation.id] = conversation
        self._save()

    def clear_conversation(self, conversation_id: str = "default") -> None:
        """Clear a conversation's history"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id] = Conversation(id=conversation_id)
            self._save()

    def list_conversations(self) -> list[str]:
        """List all conversation IDs"""
        return list(self.conversations.keys())


class ChatModule(BaseModule):
    """
    Conversational AI module for JARVIS.

    Handles natural language conversations using Ollama with
    persistent conversation history and context awareness.
    """

    name = "chat"
    description = "Natural language conversation with AI"
    version = "1.0.0"

    # Keywords that indicate a chat intent
    TASK_KEYWORDS = [
        "chat", "talk", "ask", "tell", "explain", "help",
        "what", "why", "how", "when", "where", "who",
        "can you", "could you", "would you", "please",
        "hello", "hi", "hey", "thanks", "thank you"
    ]

    # System prompt defining JARVIS personality
    SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant.

Your core principles:
1. Be helpful, direct, and efficient
2. Provide clear, actionable answers
3. Ask clarifying questions only when truly necessary
4. Be honest about limitations but focus on solutions
5. Keep responses concise unless detail is requested

You have access to various capabilities through the JARVIS system, including video editing and more. When users need these capabilities, guide them on how to use them effectively."""

    def __init__(self):
        super().__init__()
        self.memory = ConversationMemory()
        self.current_conversation_id = "default"

        if not OLLAMA_AVAILABLE:
            self.logger.warning("Ollama not installed - chat responses will be limited")

    def can_handle(self, task: str) -> bool:
        """
        Check if this module can handle the task.
        Chat module is the fallback for most conversational queries.
        """
        task_lower = task.lower()

        # Check for chat keywords
        for keyword in self.TASK_KEYWORDS:
            if keyword in task_lower:
                return True

        # Check for question patterns
        if task_lower.endswith("?"):
            return True

        # Chat module can handle most general queries as fallback
        return True

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate chat inputs"""
        if not OLLAMA_AVAILABLE:
            return True, None  # Will use fallback response
        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute a chat interaction.

        Args:
            task: The user's message
            **kwargs: Additional options
                - conversation_id: ID for conversation continuity
                - system_prompt: Override default system prompt
                - new_conversation: Start fresh conversation

        Returns:
            TaskResult with the AI response
        """
        conversation_id = kwargs.get("conversation_id", self.current_conversation_id)

        # Handle new conversation request
        if kwargs.get("new_conversation", False):
            self.memory.clear_conversation(conversation_id)
            self.logger.info(f"Started new conversation: {conversation_id}")

        # Get or create conversation
        conversation = self.memory.get_or_create(conversation_id)

        # Add user message
        conversation.add_message("user", task)

        # Generate response
        try:
            response = self._generate_response(conversation, kwargs.get("system_prompt"))

            # Add assistant response
            conversation.add_message("assistant", response)

            # Save conversation
            self.memory.save_conversation(conversation)

            return TaskResult(
                success=True,
                data=response,
                metadata={
                    "conversation_id": conversation_id,
                    "message_count": len(conversation.messages),
                    "model": settings.ollama_model
                }
            )

        except Exception as e:
            self.logger.error(f"Chat generation failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"conversation_id": conversation_id}
            )

    def _generate_response(self, conversation: Conversation, custom_system_prompt: Optional[str] = None) -> str:
        """Generate AI response using Ollama"""

        if not OLLAMA_AVAILABLE:
            return self._fallback_response(conversation.messages[-1].content if conversation.messages else "")

        try:
            # Build messages with system prompt
            system_prompt = custom_system_prompt or self.SYSTEM_PROMPT
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(conversation.get_context(max_messages=settings.chat_context_messages))

            # Call Ollama
            response = ollama.chat(
                model=settings.ollama_model,
                messages=messages,
                options={
                    "temperature": settings.chat_temperature,
                }
            )

            return response["message"]["content"]

        except Exception as e:
            self.logger.error(f"Ollama chat failed: {e}")
            raise

    def _fallback_response(self, message: str) -> str:
        """Fallback response when Ollama is unavailable"""
        return (
            "I'm currently unable to generate a full response as the AI backend (Ollama) "
            "is not available. Please ensure Ollama is installed and running.\n\n"
            f"Your message was: {message[:100]}..."
        )

    def new_conversation(self, conversation_id: Optional[str] = None) -> str:
        """Start a new conversation"""
        conv_id = conversation_id or f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.memory.clear_conversation(conv_id)
        self.current_conversation_id = conv_id
        return conv_id

    def set_conversation(self, conversation_id: str) -> None:
        """Switch to a different conversation"""
        self.current_conversation_id = conversation_id

    def get_conversation_history(self, conversation_id: Optional[str] = None) -> list[dict]:
        """Get conversation history"""
        conv_id = conversation_id or self.current_conversation_id
        conversation = self.memory.get_or_create(conv_id)
        return [asdict(m) for m in conversation.messages]

    def list_conversations(self) -> list[str]:
        """List all available conversations"""
        return self.memory.list_conversations()
