from bot.state import tournaments, chat_tournaments


def get_tournament(chat_id):
    return tournaments[chat_tournaments[chat_id]['t_id']]