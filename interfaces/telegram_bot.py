"""
Telegram Bot Interface for JARVIS

Allows users to interact with JARVIS through Telegram.
Supports:
- Natural language chat
- Task processing
- Video file handling
- User authorization
"""
import asyncio
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from core.jarvis import get_jarvis
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("telegram")


class TelegramBot:
    """
    Telegram bot interface for JARVIS.

    Features:
    - Chat with JARVIS
    - Process tasks via commands
    - Send video files for processing
    - User authorization (whitelist)
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.telegram_token
        if not self.token:
            raise ValueError(
                "Telegram token not configured. "
                "Set JARVIS_TELEGRAM_TOKEN in .env or pass token to constructor."
            )

        self.allowed_users = set(settings.telegram_allowed_users)
        self.jarvis = get_jarvis()
        self.application: Optional[Application] = None

        # Track conversation IDs per user
        self._user_conversations: dict[int, str] = {}

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        # If no whitelist configured, allow all users
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    def _get_conversation_id(self, user_id: int) -> str:
        """Get conversation ID for user"""
        if user_id not in self._user_conversations:
            self._user_conversations[user_id] = f"telegram_{user_id}"
        return self._user_conversations[user_id]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        if not self._is_authorized(user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return

        logger.info(f"User {user.id} ({user.username}) started bot")

        welcome_message = (
            f"Hello {user.first_name}! I'm JARVIS, your autonomous AI assistant.\n\n"
            "I can help you with:\n"
            "- General questions and conversations\n"
            "- Video editing tasks (send a video file)\n"
            "- Any task you can describe\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/status - Show JARVIS status\n"
            "/clear - Clear conversation history\n"
            "/help - Show help\n\n"
            "Just send me a message to start chatting!"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        if not self._is_authorized(update.effective_user.id):
            return

        help_text = (
            "JARVIS Commands:\n\n"
            "/start - Welcome message\n"
            "/status - Show system status\n"
            "/clear - Clear conversation history\n"
            "/modules - List available modules\n"
            "/help - Show this help\n\n"
            "Tips:\n"
            "- Send any message to chat with me\n"
            "- Send a video file to process it\n"
            "- Mention 'video' or 'reel' for video tasks\n"
        )
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        if not self._is_authorized(update.effective_user.id):
            return

        self.jarvis.initialize()
        status = self.jarvis.get_status()

        modules_str = ", ".join(m["name"] for m in status["modules"])
        status_text = (
            f"JARVIS Status\n\n"
            f"Initialized: {status['initialized']}\n"
            f"Modules: {modules_str}\n"
            f"Memory stats: {status['memory_stats']}"
        )
        await update.message.reply_text(status_text)

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        from modules.chat import ChatModule
        chat_module = ChatModule()
        conv_id = self._get_conversation_id(user_id)
        chat_module.clear_conversation(conv_id)

        await update.message.reply_text("Conversation history cleared.")

    async def modules_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /modules command"""
        if not self._is_authorized(update.effective_user.id):
            return

        self.jarvis.initialize()
        status = self.jarvis.get_status()

        modules_text = "Available Modules:\n\n"
        for module in status["modules"]:
            modules_text += f"- {module['name']} v{module['version']}\n"
            modules_text += f"  {module['description']}\n\n"

        await update.message.reply_text(modules_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("Sorry, you are not authorized.")
            return

        message = update.message.text
        conv_id = self._get_conversation_id(user_id)

        logger.info(f"User {user_id}: {message[:100]}...")

        # Send typing indicator
        await update.message.chat.send_action("typing")

        # Initialize JARVIS and process
        self.jarvis.initialize()

        # Process in thread pool to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.jarvis.process(message, conversation_id=conv_id)
        )

        if result.success:
            response = result.data.get("response", str(result.data))
            # Telegram has 4096 char limit
            if len(response) > 4000:
                response = response[:4000] + "\n\n[Message truncated]"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(f"Error: {result.error}")

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle video file uploads"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        await update.message.reply_text(
            "Video received! Processing will be added in a future update.\n"
            "For now, please use the CLI: `jarvis process 'create reels' --video your_video.mp4`"
        )

        # TODO: Implement video download and processing
        # video_file = await update.message.video.get_file()
        # video_path = Path(settings.videos_dir) / f"telegram_{user_id}_{video_file.file_id}.mp4"
        # await video_file.download_to_drive(video_path)
        # result = self.jarvis.process("create reels", video_path=str(video_path))

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Update {update} caused error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "An error occurred. Please try again."
            )

    def build_application(self) -> Application:
        """Build the Telegram application"""
        self.application = Application.builder().token(self.token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("modules", self.modules_command))

        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(
            MessageHandler(filters.VIDEO | filters.Document.VIDEO, self.handle_video)
        )

        # Error handler
        self.application.add_error_handler(self.error_handler)

        return self.application

    def run(self) -> None:
        """Run the bot (blocking)"""
        logger.info("Starting Telegram bot...")
        app = self.build_application()
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def run_bot(token: Optional[str] = None):
    """Convenience function to run the bot"""
    bot = TelegramBot(token)
    bot.run()


if __name__ == "__main__":
    run_bot()
