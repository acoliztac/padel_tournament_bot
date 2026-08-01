from bot.handlers.actions.tournament_actions import next_pair
from bot.services.round_service import prepare_round_edit, set_round_draw_service, prepare_round_winner_change
from bot.state import pending_management, pending_edit_selection, pending_scores, pending_manual_pair
from bot.ui.views import show_standings, show_score_buttons
from bot.utils.state_helpers import clear_management_state, clear_active_round_state
from bot.utils.tournaments_helpers import get_tournament


async def management(chat_id, context):
    pending_management[chat_id] = True
    await show_standings(chat_id, context)


async def regenerate_auto(chat_id, context):
    clear_management_state(chat_id)
    await next_pair(chat_id, context)
    return


async def regenerate_manual(chat_id, context):
    clear_management_state(chat_id)
    pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
    await show_standings(chat_id, context)
    return


async def add_to_team1(chat_id, context, data):
    player = data.split("add_to_team1_", 1)[1]
    if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team1'].append(player)
    await show_standings(chat_id, context)
    return


async def add_to_team2(chat_id, context, data):
    player = data.split("add_to_team2_", 1)[1]
    if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team2'].append(player)
    await show_standings(chat_id, context)
    return


async def remove_from_team(chat_id, context, data):
    player = data.split("remove_from_team_", 1)[1]
    if player in pending_manual_pair[chat_id]['team1']:
        pending_manual_pair[chat_id]['team1'].remove(player)
    elif player in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team2'].remove(player)
    await show_standings(chat_id, context)
    return


async def confirm_manual_pair(chat_id, context):
    tournament = get_tournament(chat_id=chat_id)

    team1 = pending_manual_pair[chat_id]['team1']
    team2 = pending_manual_pair[chat_id]['team2']

    pair = tournament.create_manual_pair(team1, team2)

    if pair is None:
        await context.bot.send_message(chat_id, "Не удалось создать команды."
                                                "\nВ каждой команде должно быть по 2 разных игрока.")
        return

    clear_management_state(chat_id)

    pending_scores[chat_id] = {'pair': pair}

    await show_standings(chat_id, context)


async def reset_manual_pair(chat_id, context):
    pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
    await show_standings(chat_id, context)
    return


async def cancel_manual_pair(chat_id, context):
    clear_management_state(chat_id)
    await show_standings(chat_id, context)
    return


async def edit_rounds(chat_id, context):
    pending_edit_selection[chat_id] = True
    await show_standings(chat_id, context)


async def edit_round(chat_id, context, data):
    round_num = int(data.split('_')[2])

    pending_data = prepare_round_edit(chat_id, round_num)

    if pending_data is None:
        await context.bot.send_message(chat_id, "Не удалось найти раунд для редактирования.")
        return


async def set_draw_round(chat_id, context, data):
    round_num = int(data.split("_")[-1])

    success = set_round_draw_service(chat_id=chat_id, round_num=round_num)

    if not success:
        await context.bot.send_message(chat_id, "Не удалось изменить результат раунда.")
        return

    await show_standings(chat_id, context, )


async def set_winner_team(chat_id, context, data):
    winner_side = ("team1" if "team1" in data else "team2")

    round_num = int(data.split("_")[-1])

    pending_data = prepare_round_winner_change(chat_id=chat_id, round_num=round_num, winner_side=winner_side)

    if pending_data is None:
        await context.bot.send_message(chat_id, "Не удалось изменить результат раунда.")
        return

    pending_scores[chat_id] = pending_data

    await show_score_buttons(chat_id=chat_id, context=context, winner_team=pending_data["winner_team"])


async def back_to_standings(chat_id, context):
    clear_management_state(chat_id)
    await show_standings(chat_id, context)
