from bot.handlers.common import show_player_selection
from bot.state import pending_new_player, players_pool


async def handle_message(update, context):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id in pending_new_player and pending_new_player[chat_id]:
        if text and text not in players_pool:
            players_pool.append(text)
        del pending_new_player[chat_id]
        await show_player_selection(update, context, chat_id)
        return