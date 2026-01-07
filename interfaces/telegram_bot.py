"""
Telegram Bot Interface for JARVIS

Provides a Telegram bot interface to interact with JARVIS chat capabilities.
Supports:
- Direct messaging with the AI
- Conversation management
- User authorization
- Async message handling
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

logger = get_logger("telegram_bot")


class TelegramBot:
    """
    Telegram bot interface for JARVIS.
    Handles incoming messages and routes them to the chat module.
    """

    def __init__(self):
        self.chat_module = ChatModule()
        self.app: Optional[Application] = None
        self._running = False

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot"""
        # If no users configured, allow everyone
        if not settings.telegram_allowed_users:
            return True
        return user_id in settings.telegram_allowed_users

    def _get_conversation_id(self, user_id: int) -> str:
        """Generate conversation ID from Telegram user ID"""
        return f"telegram_{user_id}"

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt from user {user.id}")
            return

        welcome_message = f"""Hello {user.first_name}! I'm JARVIS, your AI assistant.

I can help you with various tasks. Just send me a message and I'll do my best to assist you.

Commands:
/start - Show this message
/new - Start a new conversation
/clear - Clear conversation history
/help - Show available commands
/status - Show bot status"""

        await update.message.reply_text(welcome_message)
        logger.info(f"User {user.id} started conversation")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        help_text = """Available Commands:

/start - Start the bot and show welcome message
/new - Start a fresh conversation (clears context)
/clear - Clear your conversation history
/status - Show JARVIS system status
/help - Show this help message

Just send any message to chat with me!"""

        await update.message.reply_text(help_text)

    async def new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new command - start new conversation"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        conversation_id = self._get_conversation_id(user.id)
        self.chat_module.clear_conversation(conversation_id)
        await update.message.reply_text("Started a new conversation. Your previous context has been cleared.")
        logger.info(f"User {user.id} started new conversation")

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command - clear conversation history"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        conversation_id = self._get_conversation_id(user.id)
        self.chat_module.clear_conversation(conversation_id)
        await update.message.reply_text("Conversation history cleared.")
        logger.info(f"User {user.id} cleared conversation")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        # Get JARVIS status
        from core.jarvis import get_jarvis
        jarvis = get_jarvis()
        status = jarvis.get_status()

        # Extract module names from dict format
        modules = status['modules']
        module_names = ', '.join(
            m['name'] if isinstance(m, dict) else m for m in modules
        ) if modules else 'None'

        status_text = f"""JARVIS Status:

Initialized: {status['initialized']}
Active Modules: {module_names}

Memory Stats:
- Total Tasks: {status['memory_stats'].get('total_tasks', 0)}
- Success Rate: {status['memory_stats'].get('success_rate', 0):.1%}"""

        await update.message.reply_text(status_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        message_text = update.message.text
        conversation_id = self._get_conversation_id(user.id)

        logger.info(f"Received message from user {user.id}: {message_text[:50]}...")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        try:
            # Process through chat module
            result = self.chat_module.run(
                task="chat",
                message=message_text,
                conversation_id=conversation_id
            )

            if result.success:
                response = result.data.get("response", "I couldn't generate a response.")
                # Telegram has a 4096 character limit
                if len(response) > 4000:
                    # Split into multiple messages
                    chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
                    for chunk in chunks:
                        await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text(response)
            else:
                error_msg = f"Sorry, I encountered an error: {result.error}"
                await update.message.reply_text(error_msg)
                logger.error(f"Chat error for user {user.id}: {result.error}")

        except Exception as e:
            logger.error(f"Error handling message from user {user.id}: {e}")
            await update.message.reply_text("Sorry, something went wrong. Please try again.")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Update {update} caused error: {context.error}")

    def build_application(self) -> Application:
        """Build the Telegram application"""
        if not settings.telegram_token:
            raise ValueError("Telegram token not configured. Set JARVIS_TELEGRAM_TOKEN environment variable.")

        self.app = Application.builder().token(settings.telegram_token).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("new", self.new_command))
        self.app.add_handler(CommandHandler("clear", self.clear_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Add error handler
        self.app.add_error_handler(self.error_handler)

        return self.app

    def run(self) -> None:
        """Run the bot (blocking)"""
        logger.info("Starting Telegram bot...")
        app = self.build_application()
        self._running = True
        app.run_polling(allowed_updates=Update.ALL_TYPES)

    async def start_async(self) -> None:
        """Start the bot asynchronously"""
        logger.info("Starting Telegram bot (async)...")
        app = self.build_application()
        self._running = True
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    async def stop_async(self) -> None:
        """Stop the bot asynchronously"""
        if self.app and self._running:
            logger.info("Stopping Telegram bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._running = False


def run_telegram_bot() -> None:
    """Convenience function to run the Telegram bot"""
    bot = TelegramBot()
    bot.run()


if __name__ == "__main__":
    run_telegram_bot()
