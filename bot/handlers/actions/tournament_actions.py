import asyncio
from datetime import datetime

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import RetryAfter

from bot.handlers.common import show_standings, show_points_selection, show_tournament_mode, show_player_selection, \
    delete_score_message
from bot.state import pending_scores, tournaments, chat_tournaments, anti_spam_msg_ids, pending_edit_selection, \
    pending_manual_pair, pending_player_selection
from bot.tournament import Tournament, Player
from bot.utils.telegram_helpers import safe_delete_message, safe_edit_message_text, \
    remove_buttons_from_standings_message, delete_points_selection_message, delete_round_message, \
    delete_tournament_mode_message
from bot.utils.tournament_reports import add_final_table, add_raw_match_table, add_best_worst_partners_table, \
    add_fun_table, add_tense_matches_table, add_fair_table
from bot.utils.tournaments_helpers import get_tournament


async def create_tournament(chat_id, context):
    selected = pending_player_selection.get(chat_id, {}).get('selected', [])
    if len(selected) < 4:
        await context.bot.send_message(chat_id, "Выберите как минимум 4 игроков!")
        return

    # Save players_msg_id before overwriting chat_tournaments
    players_msg_id = chat_tournaments.get(chat_id, {}).get('players_msg_id')

    # Generate tournament name
    date_str = datetime.now().strftime("%Y-%m-%d")
    player_count = len(selected)
    name = f"{date_str}_Mexicano_{player_count}players"

    # Create tournament
    t = Tournament(name)
    for player_name in selected:
        t.add_player(Player(player_name))
    tournaments[t.id] = t
    chat_tournaments[chat_id] = {'t_id': t.id}

    # Delete player selection message
    if players_msg_id:
        await safe_delete_message(context.bot, chat_id, players_msg_id)

    if chat_id in pending_player_selection:
        del pending_player_selection[chat_id]

    await show_tournament_mode(chat_id, context)
    await show_points_selection(chat_id, context)


async def next_pair(chat_id, context):
    t = get_tournament(chat_id=chat_id)

    pair = t.select_next_pair()
    if not pair:
        await context.bot.send_message(chat_id, "Ожидание 4 игроков...")
        await show_standings(chat_id, context)
        return
    pending_scores[chat_id] = {'pair': pair}
    await show_standings(chat_id, context)


async def finalize_tournament(chat_id, context):
    t = get_tournament(chat_id=chat_id)
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    # Delete score message
    await delete_score_message(chat_id, context)

    # Delete tournament mode message
    await delete_tournament_mode_message(chat_id, context)

    # Delete round message
    await delete_round_message(chat_id, context)

    # Delete points selection message
    await delete_points_selection_message(chat_id, context)

    # Remove buttons from standings message
    await remove_buttons_from_standings_message(chat_id, context, t)

    # Show final standings without buttons
    max_name_len = max(len(p.name) for p in t.players)

    msg = ""

    # Add Fair Table (Normalized Games)
    msg = await add_fair_table(max_name_len, msg, t)

    # Add Tense Matches Table (Top 5 most intense matches)
    msg = await add_tense_matches_table(msg, t)

    # Add Fun Table (Match Interestingness)
    msg = await add_fun_table(max_name_len, msg, t)

    # Add Best/Worst Partners Table
    msg = await add_best_worst_partners_table(max_name_len, msg, t)

    # Add Raw Match Table
    msg = await add_raw_match_table(msg, t)

    # Add Final Table (Sorted by points)
    msg = await add_final_table(max_name_len, msg, t)

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML")
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await safe_edit_message_text(context.bot, chat_id, t.stats_msg_id, msg, parse_mode="HTML")
        except:
            pass  # If edit fails, just proceed
    else:
        try:
            await context.bot.send_message(chat_id, msg, parse_mode="HTML")
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    # Clear old tournament
    t_id = t.id
    del tournaments[t_id]
    del chat_tournaments[chat_id]
    if chat_id in pending_scores:
        del pending_scores[chat_id]
    if chat_id in pending_manual_pair:
        del pending_manual_pair[chat_id]
    if chat_id in pending_edit_selection:
        del pending_edit_selection[chat_id]

    # --- Start new tournament button ---
    keyboard = [[InlineKeyboardButton("Начать новый турнир", callback_data="start_new_tournament")]]
    try:
        await context.bot.send_message(chat_id, "Начать новый турнир?", reply_markup=InlineKeyboardMarkup(keyboard))
    except RetryAfter as e:
        try:
            sent_anti = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
            anti_spam_msg_ids[chat_id] = sent_anti.message_id
        except:
            pass
        await asyncio.sleep(e.retry_after)
        await context.bot.send_message(chat_id, "Начать новый турнир?", reply_markup=InlineKeyboardMarkup(keyboard))


async def start_new_tournament(chat_id, query, context):
    pending_player_selection[chat_id] = {'selected': []}
    await show_player_selection(query, context, chat_id)
    await safe_delete_message(context.bot, chat_id, query.message.message_id)
    return


async def set_round_points(chat_id, data, context):
    t = get_tournament(chat_id=chat_id)
    points = int(data.split("_")[-1])
    t.round_points = points
    # Delete points selection message
    if chat_tournaments[chat_id].get('points_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['points_msg_id'])
    await show_standings(chat_id, context)
    await next_pair(chat_id, context)
