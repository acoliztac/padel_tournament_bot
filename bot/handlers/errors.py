import logging

from telegram.error import RetryAfter

logger = logging.getLogger(__name__)


async def error_handler(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    if update and update.effective_chat:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Произошла ошибка. Пожалуйста, попробуйте снова.")
        except RetryAfter:
            pass  # Avoid sending message if flood control is active
