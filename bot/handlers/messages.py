from bot.state import pending_new_player, players_pool
from bot.ui.views import show_player_selection


async def handle_message(update, context):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if pending_new_player.get(chat_id):
        if text and text not in players_pool:
            players_pool.append(text)
        del pending_new_player[chat_id]
        await show_player_selection(update, context, chat_id)
        return