from bot.services.tournament_service import (
    create_tournament_service,
    finalize_tournament_service,
    select_next_pair_service,
    set_round_points_service,
)
from bot.state import chat_tournaments, pending_player_selection
from bot.ui.views import (
    build_final_report,
    delete_score_message,
    show_final_report,
    show_new_tournament_button,
    show_player_selection,
    show_points_selection,
    show_standings,
    show_tournament_mode,
)
from bot.utils.telegram_helpers import (
    safe_delete_message,
    safe_delete_player_selection_message,
    safe_delete_points_selection_message,
    safe_delete_round_message,
    safe_delete_tournament_mode_message,
    safe_remove_buttons_from_standings_message,
)


async def create_tournament(chat_id, context):
    selected = pending_player_selection.get(chat_id, {}).get('selected', [])
    if len(selected) < 4:
        await context.bot.send_message(chat_id, "Выберите как минимум 4 игроков!")
        return

    await safe_delete_player_selection_message(chat_id, context)

    create_tournament_service(chat_id, selected)

    pending_player_selection.pop(chat_id, None)

    await show_tournament_mode(chat_id, context)
    await show_points_selection(chat_id, context)


async def next_pair(chat_id, context):
    pair = select_next_pair_service(chat_id)

    if not pair:
        await context.bot.send_message(chat_id, "Ожидание 4 игроков...")
        await show_standings(chat_id, context)
        return

    await show_standings(chat_id, context)


async def finalize_tournament(chat_id, context):
    t = finalize_tournament_service(chat_id)

    await delete_score_message(chat_id, context)
    await safe_delete_tournament_mode_message(chat_id, context)
    await safe_delete_round_message(chat_id, context)
    await safe_delete_points_selection_message(chat_id, context)

    await safe_remove_buttons_from_standings_message(chat_id, context, t)

    msg = build_final_report(t)
    await show_final_report(chat_id, context, msg, t.stats_msg_id)

    await show_new_tournament_button(chat_id, context)
    chat_tournaments.pop(chat_id, None)


async def begin_tournament_setup(chat_id, query, context):
    pending_player_selection[chat_id] = {'selected': []}
    await show_player_selection(query, context, chat_id)
    await safe_delete_message(context.bot, chat_id, query.message.message_id)


async def set_round_points(chat_id, data, context):
    points = int(data.split("_")[-1])
    set_round_points_service(chat_id, points)

    await safe_delete_points_selection_message(chat_id, context)

    await show_standings(chat_id, context)
    await next_pair(chat_id, context)
