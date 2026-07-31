import logging
import os

from dotenv import load_dotenv
from telegram import Update, ForceReply
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from bot.handlers.callbacks import handle_callback
from bot.handlers.common import show_player_selection, show_tournament_mode
from bot.handlers.errors import error_handler
from bot.handlers.messages import handle_message
from bot.state import (
    chat_tournaments,
    pending_new_player,
    pending_player_selection,
    players_pool
)
from bot.utils.telegram_helpers import safe_delete_message

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_tournaments:
        await show_tournament_mode(chat_id, context)
        await safe_delete_message(context.bot, chat_id, update.message.message_id)
        return

    pending_player_selection[chat_id] = {'selected': []}

    if not players_pool:
        await update.message.reply_text("В списке нет игроков. Добавьте нового игрока:")
        pending_new_player[chat_id] = True
        await context.bot.send_message(chat_id, "Введите имя игрока:", reply_markup=ForceReply())
    else:
        await show_player_selection(update, context, chat_id)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
