async def safe_delete_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
    except:
        pass


async def safe_edit_message_reply_markup(bot, chat_id, message_id, reply_markup=None):
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except:
        pass
