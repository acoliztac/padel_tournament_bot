from bot.state import chat_tournaments


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


async def safe_edit_message_text(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None):
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except:
        return False


async def remove_buttons_from_standings_message(chat_id, context, t):
    if t.stats_msg_id:
        await safe_edit_message_reply_markup(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id,
                                             reply_markup=None)


async def delete_points_selection_message(chat_id, context):
    if chat_tournaments[chat_id].get('points_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['points_msg_id'])


async def delete_round_message(chat_id, context):
    if chat_tournaments[chat_id].get('round_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['round_msg_id'])


async def delete_tournament_mode_message(chat_id, context):
    if chat_tournaments[chat_id].get('tournament_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['tournament_msg_id'])
