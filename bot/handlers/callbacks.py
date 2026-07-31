from bot.handlers.common import (
    show_player_selection,
)
from bot.handlers.tournament_actions import (
    finalize_tournament,
    create_tournament,
    start_new_tournament,
    add_new_player,
    select_all_players,
    delete_player,
    confirm_delete,
    select_player,
    deselect_player,
    edit_last_round,
    set_round_points,
    result_draw,
    result_team,
    set_score,
    cancel_manual_pair,
    reset_manual_pair,
    confirm_manual_pair,
    remove_from_team,
    add_to_team2,
    add_to_team1,
    regenerate_manual,
    regenerate_auto,
    management,
    edit_rounds,
    back_to_standings,
    set_winner_team,
    set_draw_round,
    edit_round
)
from bot.state import chat_tournaments


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if chat_id not in chat_tournaments:
        allowed_without_tournament = {
            "create_tournament",
            "start_new_tournament",
        }

        if data not in allowed_without_tournament:
            return

    if data == "create_tournament":
        await create_tournament(chat_id=chat_id, context=context)

    elif data == "start_new_tournament":
        await start_new_tournament(chat_id=chat_id, query=query, context=context)

    elif data == "add_new_player":
        await add_new_player(chat_id=chat_id, context=context)

    elif data == "select_all_players":
        await select_all_players(chat_id=chat_id, query=query, context=context)

    elif data == "delete_player":
        await delete_player(chat_id=chat_id, query=query, context=context)

    elif data.startswith("confirm_delete_"):
        await confirm_delete(chat_id=chat_id, query=query, context=context, data=data)

    elif data == "back_to_selection":
        await show_player_selection(query=query, context=context, chat_id=chat_id)

    elif data.startswith("select_player_"):
        await select_player(chat_id=chat_id, context=context, query=query, data=data)

    elif data.startswith("deselect_player_"):
        await deselect_player(chat_id=chat_id, query=query, context=context, data=data)

    elif data == "finish_tournament":
        await finalize_tournament(chat_id=chat_id, context=context)

    elif data == "edit_last_round":
        await edit_last_round(chat_id=chat_id, context=context)

    elif data.startswith("set_round_points_"):
        await set_round_points(chat_id=chat_id, data=data, context=context)

    elif data == "result_draw":
        await result_draw(chat_id=chat_id, context=context)

    elif data in ["result_team1", "result_team2"]:
        await result_team(chat_id=chat_id, context=context, data=data)

    elif data.startswith("set_score_"):
        await set_score(chat_id=chat_id, data=data, context=context)

    elif data.startswith("edit_round_"):
        await edit_round(chat_id=chat_id, context=context, data=data)

    elif data.startswith("set_draw_round_"):
        await set_draw_round(chat_id=chat_id, context=context, data=data)

    elif data.startswith("set_winner_team"):
        await set_winner_team(chat_id=chat_id, context=context, data=data)

    elif data == "back_to_standings":
        await back_to_standings(chat_id=chat_id, context=context)

    elif data == "edit_rounds":
        await edit_rounds(chat_id=chat_id, context=context)

    elif data == "management":
        await management(chat_id=chat_id, context=context)

    elif data == "regenerate_auto":
        await regenerate_auto(chat_id=chat_id, context=context)

    elif data == "regenerate_manual":
        await regenerate_manual(chat_id=chat_id, context=context)

    elif data.startswith("add_to_team1_"):
        await add_to_team1(chat_id=chat_id, context=context, data=data)

    elif data.startswith("add_to_team2_"):
        await add_to_team2(chat_id=chat_id, context=context, data=data)

    elif data.startswith("remove_from_team_"):
        await remove_from_team(chat_id=chat_id, context=context, data=data)

    elif data == "confirm_manual_pair":
        await confirm_manual_pair(chat_id=chat_id, context=context)

    elif data == "reset_manual_pair":
        await reset_manual_pair(chat_id=chat_id, context=context)

    elif data == "cancel_manual_pair":
        await cancel_manual_pair(chat_id=chat_id, context=context)
