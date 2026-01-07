"""
Chat Module - Conversational AI for JARVIS

Features:
- Natural language conversation with Ollama LLM
- Conversation history management
- System prompt customization
- Context-aware responses
"""
from dataclasses import dataclass, field
from typing import Optional
import json

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("chat")


@dataclass
class Message:
    """A chat message"""
    role: str  # "system", "user", or "assistant"
    content: str


@dataclass
class Conversation:
    """A conversation with message history"""
    id: str
    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def to_ollama_format(self) -> list[dict]:
        """Convert to Ollama chat format"""
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        for msg in self.messages:
            result.append({"role": msg.role, "content": msg.content})
        return result

    def clear(self) -> None:
        """Clear conversation history"""
        self.messages = []


class ChatModule(BaseModule):
    """
    Conversational AI module using Ollama.

    Handles natural language conversations, questions, and general chat.
    """

    name = "chat"
    description = "Conversational AI for natural language interaction"
    version = "0.1.0"

    # Keywords that indicate chat/conversation tasks
    TASK_KEYWORDS = [
        "chat", "talk", "ask", "question", "tell", "explain", "help",
        "what", "how", "why", "when", "where", "who", "can you",
        "please", "thanks", "hello", "hi", "hey"
    ]

    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant. You are:
- Helpful, accurate, and concise
- Direct and to the point
- Knowledgeable about technology, coding, and general topics
- Able to admit when you don't know something
- Never making up information

If asked to perform a task that requires specific modules (like video editing),
suggest using the appropriate JARVIS module instead."""

    def __init__(self):
        super().__init__()
        self._conversations: dict[str, Conversation] = {}
        self._default_conversation = "default"
        self._ollama_client = None

    def can_handle(self, task: str) -> bool:
        """Check if this is a chat/conversation task"""
        task_lower = task.lower()
        # Chat module is the default handler - it can handle anything
        # that isn't specifically handled by other modules
        return any(kw in task_lower for kw in self.TASK_KEYWORDS)

    def get_or_create_conversation(
        self,
        conversation_id: str = "default",
        system_prompt: Optional[str] = None
    ) -> Conversation:
        """Get existing conversation or create new one"""
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = Conversation(
                id=conversation_id,
                system_prompt=system_prompt or self.DEFAULT_SYSTEM_PROMPT
            )
        return self._conversations[conversation_id]

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Process a chat message and return response"""
        conversation_id = kwargs.get("conversation_id", self._default_conversation)
        system_prompt = kwargs.get("system_prompt")
        stream = kwargs.get("stream", False)

        # Get or create conversation
        conversation = self.get_or_create_conversation(conversation_id, system_prompt)

        # Add user message
        conversation.add_message("user", task)

        try:
            # Get response from Ollama
            response = self._chat_with_ollama(conversation, stream=stream)

            # Add assistant response to history
            conversation.add_message("assistant", response)

            return TaskResult(
                success=True,
                data={
                    "response": response,
                    "conversation_id": conversation_id,
                    "message_count": len(conversation.messages)
                },
                metadata={
                    "model": settings.ollama_model,
                    "stream": stream
                }
            )

        except Exception as e:
            self.logger.error(f"Chat failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                data={"conversation_id": conversation_id}
            )

    def _chat_with_ollama(self, conversation: Conversation, stream: bool = False) -> str:
        """Send conversation to Ollama and get response"""
        try:
            import ollama
        except ImportError:
            raise RuntimeError("ollama not installed. Run: pip install ollama")

        messages = conversation.to_ollama_format()

        self.logger.debug(f"Sending {len(messages)} messages to {settings.ollama_model}")

        if stream:
            # Streaming response
            full_response = ""
            for chunk in ollama.chat(
                model=settings.ollama_model,
                messages=messages,
                stream=True
            ):
                content = chunk.get("message", {}).get("content", "")
                full_response += content
            return full_response
        else:
            # Non-streaming response
            response = ollama.chat(
                model=settings.ollama_model,
                messages=messages
            )
            return response["message"]["content"]

    def new_conversation(
        self,
        conversation_id: str,
        system_prompt: Optional[str] = None
    ) -> Conversation:
        """Start a new conversation"""
        self._conversations[conversation_id] = Conversation(
            id=conversation_id,
            system_prompt=system_prompt or self.DEFAULT_SYSTEM_PROMPT
        )
        return self._conversations[conversation_id]

    def clear_conversation(self, conversation_id: str = "default") -> bool:
        """Clear a conversation's history"""
        if conversation_id in self._conversations:
            self._conversations[conversation_id].clear()
            return True
        return False

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation entirely"""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def list_conversations(self) -> list[dict]:
        """List all active conversations"""
        return [
            {
                "id": conv.id,
                "message_count": len(conv.messages),
                "has_system_prompt": bool(conv.system_prompt)
            }
            for conv in self._conversations.values()
        ]

    def get_history(self, conversation_id: str = "default") -> list[dict]:
        """Get conversation history"""
        if conversation_id not in self._conversations:
            return []
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self._conversations[conversation_id].messages
        ]
