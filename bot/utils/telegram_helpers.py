from telegram.error import TelegramError

from bot.state import chat_tournaments, pending_scores


async def safe_delete_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
    except TelegramError:
        pass


async def safe_edit_message_reply_markup(bot, chat_id, message_id, reply_markup=None):
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except TelegramError:
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
    except TelegramError:
        return False


async def safe_remove_buttons_from_standings_message(chat_id, context, t):
    if t.stats_msg_id:
        await safe_edit_message_reply_markup(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id,
                                             reply_markup=None)


async def safe_delete_points_selection_message(chat_id, context):
    if chat_tournaments[chat_id].get('points_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['points_msg_id'])


async def safe_delete_round_message(chat_id, context):
    if chat_tournaments[chat_id].get('round_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['round_msg_id'])


async def safe_delete_tournament_mode_message(chat_id, context):
    if chat_tournaments[chat_id].get('tournament_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['tournament_msg_id'])


async def safe_delete_player_selection_message(chat_id, context):
    if chat_tournaments[chat_id].get('players_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['players_msg_id'])

async def safe_delete_score_message(chat_id, context):
    if chat_id in pending_scores and pending_scores[chat_id].get('score_msg_id'):
        await safe_delete_message(context.bot, chat_id, pending_scores[chat_id]['score_msg_id'])

