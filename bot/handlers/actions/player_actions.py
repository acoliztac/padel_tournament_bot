from telegram import ForceReply

from bot.state import pending_new_player, pending_player_selection, players_pool
from bot.ui.views import show_player_selection


async def add_new_player(chat_id, context):
    pending_new_player[chat_id] = True
    await context.bot.send_message(chat_id, "Введите имя игрока:", reply_markup=ForceReply())


async def delete_player(chat_id, query, context):
    selected = pending_player_selection[chat_id]['selected']
    for name in selected:
        if name in players_pool:
            players_pool.remove(name)
    pending_player_selection[chat_id]['selected'] = []
    await show_player_selection(query, context, chat_id)


async def confirm_delete(chat_id, query, context, data):
    name = data.split("confirm_delete_")[1]
    pending_player_selection[chat_id]['selected'].remove(name)
    if name in players_pool:
        players_pool.remove(name)
    await show_player_selection(query, context, chat_id)


async def select_player(chat_id, context, query, data):
    idx = int(data.split("_")[2])
    if idx < len(players_pool):
        pending_player_selection[chat_id]['selected'].append(players_pool[idx])
        await show_player_selection(query, context, chat_id)


async def deselect_player(chat_id, data, query, context):
    idx = int(data.split("_")[2])
    if idx < len(players_pool):
        pending_player_selection[chat_id]['selected'].remove(players_pool[idx])
        await show_player_selection(query, context, chat_id)


async def select_all_players(chat_id, query, context):
    pending_player_selection[chat_id]['selected'] = list(players_pool)
    await show_player_selection(query, context, chat_id)
