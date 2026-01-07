"""
Telegram Bot Interface for JARVIS
Allows chat via Telegram.
"""
import asyncio
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from modules.chat_module import ChatModule
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("telegram")


class TelegramBot:
    """Telegram bot for JARVIS chat interface"""

    def __init__(self):
        self.chat_module = ChatModule()
        self.user_conversations: dict[int, str] = {}  # user_id -> conversation_id

    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot"""
        if not settings.telegram_allowed_users:
            return True  # No restrictions if list is empty
        return user_id in settings.telegram_allowed_users

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        if not self.is_authorized(user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        # Create new conversation for user
        conversation = self.chat_module.new_conversation()
        self.user_conversations[user.id] = conversation.id

        await update.message.reply_text(
            f"Hello {user.first_name}! I'm JARVIS, your AI assistant.\n\n"
            "Commands:\n"
            "/new - Start new conversation\n"
            "/clear - Clear current conversation\n"
            "/status - Check system status\n"
            "/help - Show this help"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        if not self.is_authorized(update.effective_user.id):
            return

        await update.message.reply_text(
            "JARVIS Commands:\n\n"
            "/new - Start new conversation\n"
            "/clear - Clear current conversation\n"
            "/status - Check system status\n"
            "/help - Show this help\n\n"
            "Just send a message to chat with me!"
        )

    async def new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new command - Start new conversation"""
        user_id = update.effective_user.id
        if not self.is_authorized(user_id):
            return

        conversation = self.chat_module.new_conversation()
        self.user_conversations[user_id] = conversation.id
        await update.message.reply_text("Started new conversation. How can I help you?")

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command - Clear conversation history"""
        user_id = update.effective_user.id
        if not self.is_authorized(user_id):
            return

        conv_id = self.user_conversations.get(user_id)
        if conv_id:
            self.chat_module.clear_conversation(conv_id)
            await update.message.reply_text("Conversation cleared.")
        else:
            await update.message.reply_text("No active conversation.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        if not self.is_authorized(update.effective_user.id):
            return

        ollama_ok = self.chat_module.check_ollama_health()
        status_emoji = "✅" if ollama_ok else "❌"

        await update.message.reply_text(
            f"JARVIS Status:\n\n"
            f"Ollama: {status_emoji} {'Online' if ollama_ok else 'Offline'}\n"
            f"Model: {settings.chat_model}"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages"""
        user = update.effective_user
        if not self.is_authorized(user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        message_text = update.message.text
        if not message_text:
            return

        # Check Ollama health
        if not self.chat_module.check_ollama_health():
            await update.message.reply_text(
                "Sorry, the AI service is currently unavailable. Please try again later."
            )
            return

        # Get or create conversation for user
        conv_id = self.user_conversations.get(user.id)
        if not conv_id:
            conversation = self.chat_module.new_conversation()
            self.user_conversations[user.id] = conversation.id
            conv_id = conversation.id

        # Send typing indicator
        await update.message.chat.send_action("typing")

        try:
            # Get response
            response, conversation = self.chat_module.chat(message_text, conv_id)

            # Send response (split if too long)
            max_length = 4096
            if len(response) <= max_length:
                await update.message.reply_text(response)
            else:
                # Split into chunks
                for i in range(0, len(response), max_length):
                    chunk = response[i:i + max_length]
                    await update.message.reply_text(chunk)

        except Exception as e:
            logger.error(f"Chat error for user {user.id}: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error processing your message. Please try again."
            )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Telegram error: {context.error}")


def run_bot():
    """Start the Telegram bot"""
    if not settings.telegram_token:
        raise ValueError("JARVIS_TELEGRAM_TOKEN not set")

    bot = TelegramBot()

    # Create application
    application = Application.builder().token(settings.telegram_token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("new", bot.new_command))
    application.add_handler(CommandHandler("clear", bot.clear_command))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_error_handler(bot.error_handler)

    # Start bot
    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
