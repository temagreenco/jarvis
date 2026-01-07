"""Tests for ChatModule"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import json

from modules.chat_module import (
    ChatModule,
    ConversationStore,
    Conversation,
    Message,
    check_ollama_available
)


class TestMessage:
    """Tests for Message dataclass"""

    def test_message_creation(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None

    def test_message_with_timestamp(self):
        msg = Message(role="assistant", content="Hi", timestamp="2024-01-01T00:00:00")
        assert msg.timestamp == "2024-01-01T00:00:00"


class TestConversation:
    """Tests for Conversation dataclass"""

    def test_conversation_creation(self):
        conv = Conversation(id="test-123")
        assert conv.id == "test-123"
        assert conv.messages == []
        assert conv.metadata == {}

    def test_add_message(self):
        conv = Conversation(id="test")
        msg = conv.add_message("user", "Hello")
        assert len(conv.messages) == 1
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_get_context(self):
        conv = Conversation(id="test")
        conv.add_message("user", "Hello")
        conv.add_message("assistant", "Hi there")

        context = conv.get_context()
        assert len(context) == 2
        assert context[0] == {"role": "user", "content": "Hello"}
        assert context[1] == {"role": "assistant", "content": "Hi there"}

    def test_get_context_max_messages(self):
        conv = Conversation(id="test")
        for i in range(30):
            conv.add_message("user", f"Message {i}")

        context = conv.get_context(max_messages=10)
        assert len(context) == 10
        # Should get the last 10 messages
        assert context[0]["content"] == "Message 20"

    def test_clear(self):
        conv = Conversation(id="test")
        conv.add_message("user", "Hello")
        conv.clear()
        assert conv.messages == []


class TestConversationStore:
    """Tests for ConversationStore"""

    def test_store_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConversationStore(Path(tmpdir) / "convs.json")
            assert store.conversations == {}

    def test_get_or_create(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConversationStore(Path(tmpdir) / "convs.json")
            conv = store.get_or_create("test-id")
            assert conv.id == "test-id"
            assert "test-id" in store.conversations

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "convs.json"

            # Create and save
            store1 = ConversationStore(path)
            conv = store1.get_or_create("test-id")
            conv.add_message("user", "Hello")
            store1.save(conv)

            # Load in new store
            store2 = ConversationStore(path)
            conv2 = store2.get_or_create("test-id")
            assert len(conv2.messages) == 1
            assert conv2.messages[0].content == "Hello"

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConversationStore(Path(tmpdir) / "convs.json")
            store.get_or_create("test-id")
            assert store.delete("test-id") is True
            assert "test-id" not in store.conversations
            assert store.delete("nonexistent") is False

    def test_list_conversations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConversationStore(Path(tmpdir) / "convs.json")
            store.get_or_create("id1")
            store.get_or_create("id2")
            store.get_or_create("id3")

            convs = store.list_conversations(limit=2)
            assert len(convs) == 2


class TestChatModule:
    """Tests for ChatModule"""

    def test_module_properties(self):
        module = ChatModule()
        assert module.name == "chat"
        assert module.version == "0.1.0"

    def test_can_handle(self):
        module = ChatModule()
        assert module.can_handle("chat with me") is True
        assert module.can_handle("ask a question") is True
        assert module.can_handle("what is Python") is True
        assert module.can_handle("help me") is True
        assert module.can_handle("process video") is False

    def test_validate_inputs(self):
        module = ChatModule()
        valid, error = module.validate_inputs(message="Hello")
        assert valid is True
        assert error is None

        valid, error = module.validate_inputs()
        assert valid is False
        assert "message is required" in error

    def test_new_conversation(self):
        module = ChatModule()
        conv_id = module.new_conversation()
        assert conv_id is not None
        assert len(conv_id) == 8

    def test_new_conversation_with_id(self):
        module = ChatModule()
        conv_id = module.new_conversation("my-custom-id")
        assert conv_id == "my-custom-id"

    def test_clear_conversation(self):
        module = ChatModule()
        conv_id = module.new_conversation()
        # Add some messages by getting the conversation
        conv = module.store.get_or_create(conv_id)
        conv.add_message("user", "test")
        module.store.save(conv)

        result = module.clear_conversation(conv_id)
        assert result is True

        # Check messages are cleared
        conv = module.store.get_or_create(conv_id)
        assert len(conv.messages) == 0

    def test_list_conversations(self):
        module = ChatModule()
        module.new_conversation("list-test-1")
        module.new_conversation("list-test-2")

        convs = module.list_conversations(limit=10)
        ids = [c["id"] for c in convs]
        assert "list-test-1" in ids
        assert "list-test-2" in ids

    def test_is_available(self):
        module = ChatModule()
        available, msg = module.is_available()
        # Will be False if Ollama isn't running
        assert isinstance(available, bool)
        assert isinstance(msg, str)

    @patch('modules.chat_module.httpx.Client')
    def test_execute_success(self, mock_client):
        """Test successful chat execution with mocked Ollama"""
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Hello! How can I help you?"}
        }
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        module = ChatModule()
        result = module.execute(
            task="chat",
            message="Hello",
            conversation_id="test-exec"
        )

        assert result.success is True
        assert "response" in result.data
        assert result.data["response"] == "Hello! How can I help you?"

    @patch('modules.chat_module.httpx.Client')
    def test_execute_connection_error(self, mock_client):
        """Test chat execution with connection error"""
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        module = ChatModule()
        result = module.execute(
            task="chat",
            message="Hello",
            conversation_id="test-error"
        )

        assert result.success is False
        assert "Ollama" in result.error


class TestCheckOllamaAvailable:
    """Tests for check_ollama_available function"""

    @patch('modules.chat_module.httpx.Client')
    def test_ollama_available(self, mock_client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        available, msg = check_ollama_available()
        assert available is True
        assert "available" in msg.lower()

    @patch('modules.chat_module.httpx.Client')
    def test_ollama_unavailable(self, mock_client):
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        available, msg = check_ollama_available()
        assert available is False
        assert "Cannot connect" in msg
