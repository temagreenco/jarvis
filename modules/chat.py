"""
Chat Module - Conversational AI interface for JARVIS
Handles natural language conversations using local LLMs via Ollama.
"""
from typing import Optional
import ollama
from ollama import ResponseError

from modules.base_module import BaseModule, TaskResult
from config.settings import get_settings


class ChatModule(BaseModule):
    """
    Chat module for conversational AI interactions.

    Uses Ollama for local LLM inference. Maintains conversation
    history for context-aware responses.
    """

    name: str = "chat"
    description: str = "Conversational AI assistant using local LLMs"
    version: str = "0.1.0"

    # Keywords that trigger this module
    KEYWORDS = [
        "chat", "message", "ask", "tell", "talk", "conversation",
        "question", "answer", "help", "explain", "what", "how",
        "why", "when", "where", "who", "can you", "please"
    ]

    def __init__(self, system_prompt: Optional[str] = None):
        super().__init__()
        self.settings = get_settings()
        self.conversation_history: list[dict] = []
        self.system_prompt = system_prompt or self._default_system_prompt()
        self._client: Optional[ollama.Client] = None

    def _default_system_prompt(self) -> str:
        """Default system prompt for JARVIS chat"""
        return """You are JARVIS, an advanced AI assistant. You are helpful, knowledgeable, and efficient.

Your core principles:
1. If asked to do something - provide clear, actionable guidance
2. If you don't know something - be honest about it
3. Keep responses concise but complete
4. Be proactive in offering relevant information
5. Maintain a professional yet friendly tone

You have access to various capabilities including video editing, and more modules are being developed.
When users ask about tasks you can help with, guide them on how to phrase their requests."""

    @property
    def client(self) -> ollama.Client:
        """Lazy-load Ollama client"""
        if self._client is None:
            self._client = ollama.Client(host=self.settings.ollama_host)
        return self._client

    def can_handle(self, task: str) -> bool:
        """
        Check if this module can handle the task.
        Chat module has low priority - it handles most text inputs
        that don't match other specific modules.
        """
        task_lower = task.lower()
        # Check for keywords
        for keyword in self.KEYWORDS:
            if keyword in task_lower:
                return True
        # Chat is the fallback for conversational inputs
        # If it looks like a question or statement, handle it
        if task.strip().endswith("?"):
            return True
        return False

    def execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute a chat interaction.

        Args:
            task: The user's message/question
            **kwargs: Additional options
                - stream: bool - Whether to stream the response (default: False)
                - temperature: float - Response creativity (0.0-1.0)
                - max_tokens: int - Maximum response length
                - clear_history: bool - Clear conversation history before this message

        Returns:
            TaskResult with the assistant's response
        """
        stream = kwargs.get("stream", False)
        temperature = kwargs.get("temperature", self.settings.chat_temperature)
        max_tokens = kwargs.get("max_tokens", self.settings.chat_max_tokens)
        clear_history = kwargs.get("clear_history", False)

        if clear_history:
            self.clear_history()

        try:
            # Build messages list with history
            messages = self._build_messages(task)

            # Call Ollama
            response = self.client.chat(
                model=self.settings.chat_model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
                stream=stream
            )

            if stream:
                # Return generator for streaming
                return TaskResult(
                    success=True,
                    data=self._stream_response(response, task),
                    metadata={"streaming": True}
                )
            else:
                # Get response content
                assistant_message = response["message"]["content"]

                # Add to history
                self._add_to_history("user", task)
                self._add_to_history("assistant", assistant_message)

                return TaskResult(
                    success=True,
                    data=assistant_message,
                    metadata={
                        "model": self.settings.chat_model,
                        "history_length": len(self.conversation_history)
                    }
                )

        except ResponseError as e:
            self.logger.error(f"Ollama error: {e}")
            return TaskResult(
                success=False,
                error=f"LLM error: {str(e)}",
                metadata={"error_type": "ollama_error"}
            )
        except Exception as e:
            self.logger.error(f"Chat execution failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                metadata={"error_type": "execution_error"}
            )

    def _build_messages(self, current_message: str) -> list[dict]:
        """Build the messages list including system prompt and history"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add conversation history (limited by context window setting)
        max_history = self.settings.chat_context_messages
        history_slice = self.conversation_history[-max_history:] if max_history > 0 else []
        messages.extend(history_slice)

        # Add current message
        messages.append({"role": "user", "content": current_message})

        return messages

    def _add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # Trim history if it exceeds max size
        max_history = self.settings.chat_max_history
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]

    def _stream_response(self, response_stream, user_message: str):
        """Generator for streaming responses"""
        full_response = ""
        for chunk in response_stream:
            if "message" in chunk and "content" in chunk["message"]:
                content = chunk["message"]["content"]
                full_response += content
                yield content

        # After streaming completes, add to history
        self._add_to_history("user", user_message)
        self._add_to_history("assistant", full_response)

    def clear_history(self) -> None:
        """Clear conversation history"""
        self.conversation_history = []
        self.logger.info("Conversation history cleared")

    def set_system_prompt(self, prompt: str) -> None:
        """Update the system prompt"""
        self.system_prompt = prompt
        self.logger.info("System prompt updated")

    def get_history(self) -> list[dict]:
        """Get current conversation history"""
        return self.conversation_history.copy()
