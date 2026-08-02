from bot.handlers.actions.management_actions import (
    add_to_team1,
    add_to_team2,
    back_to_standings,
    cancel_manual_pair,
    confirm_manual_pair,
    edit_round,
    edit_rounds,
    management,
    regenerate_auto,
    regenerate_manual,
    remove_from_team,
    reset_manual_pair,
    set_draw_round,
    set_winner_team,
)
from bot.handlers.actions.player_actions import (
    add_new_player,
    confirm_delete,
    delete_player,
    deselect_player,
    select_all_players,
    select_player,
)
from bot.handlers.actions.round_actions import result_team, set_draw, set_score
from bot.handlers.actions.tournament_actions import (
    begin_tournament_setup,
    create_tournament,
    finalize_tournament,
    set_round_points,
)
from bot.state import chat_tournaments
from bot.ui.views import show_player_selection


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if chat_id not in chat_tournaments:
        allowed_without_tournament = {
            "create_tournament",
            "begin_tournament_setup",
        }

        if data not in allowed_without_tournament:
            return

    if data == "create_tournament":
        await create_tournament(chat_id=chat_id, context=context)

    elif data == "begin_tournament_setup":
        await begin_tournament_setup(chat_id=chat_id, query=query, context=context)

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

    elif data.startswith("set_round_points_"):
        await set_round_points(chat_id=chat_id, data=data, context=context)

    elif data == "set_draw":
        await set_draw(chat_id=chat_id, context=context)

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
