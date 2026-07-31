from bot.handlers.actions.tournament_actions import next_pair
from bot.handlers.common import show_standings, show_score_buttons
from bot.state import pending_management, pending_edit_selection, pending_scores, pending_manual_pair, pending_regenerate_menu
from bot.tournament import Pair
from bot.utils.tournaments_helpers import get_tournament


async def management(chat_id, context):
    pending_management[chat_id] = True
    await show_standings(chat_id, context)


async def regenerate_auto(chat_id, context):
    if chat_id in pending_regenerate_menu:
        del pending_regenerate_menu[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
    if chat_id in pending_scores:
        del pending_scores[chat_id]
    await next_pair(chat_id, context)
    return


async def regenerate_manual(chat_id, context):
    if chat_id in pending_regenerate_menu:
        del pending_regenerate_menu[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
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
    t = get_tournament(chat_id=chat_id)
    team1_names = pending_manual_pair[chat_id]['team1']
    team2_names = pending_manual_pair[chat_id]['team2']
    if len(team1_names) != 2 or len(team2_names) != 2:
        await context.bot.send_message(chat_id, "Каждая команда должна иметь ровно 2 игрока!")
        return
    # Create pair
    team1 = [p for p in t.players if p.name in team1_names]
    team2 = [p for p in t.players if p.name in team2_names]
    pair = Pair(team1, team2)
    for p in team1 + team2:
        p.current_pair = pair
    if chat_id in pending_management:
        del pending_management[chat_id]
    pending_scores[chat_id] = {'pair': pair}
    del pending_manual_pair[chat_id]
    await show_standings(chat_id, context)
    return


async def reset_manual_pair(chat_id, context):
    pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
    await show_standings(chat_id, context)
    return


async def cancel_manual_pair(chat_id, context):
    del pending_manual_pair[chat_id]
    await show_standings(chat_id, context)
    return


async def edit_rounds(chat_id, context):
    pending_edit_selection[chat_id] = True
    await show_standings(chat_id, context)


async def edit_round(chat_id, context, data):
    t = get_tournament(chat_id=chat_id)
    round_num = int(data.split('_')[2])
    for i, r in enumerate(t.round_history):
        if r['round'] == round_num:
            # Rollback statistics
            team1_names = r["team1"]
            team2_names = r["team2"]
            score_str = r["score"]
            team1_score, team2_score = map(int, score_str.split("-"))

            # Find players
            team1 = [p for p in t.players if p.name in team1_names]
            team2 = [p for p in t.players if p.name in team2_names]

            # Rollback games_played
            for p in team1 + team2:
                p.games_played -= 1

            # Rollback wins, draws, losses, points
            if team1_score == team2_score:
                for p in team1 + team2:
                    p.draws -= 1
                    p.points -= team1_score
            elif team1_score > team2_score:
                for p in team1:
                    p.wins -= 1
                    p.points -= team1_score
                for p in team2:
                    p.losses -= 1
                    p.points -= team2_score
            else:
                for p in team1:
                    p.losses -= 1
                    p.points -= team1_score
                for p in team2:
                    p.wins -= 1
                    p.points -= team2_score

            # Create pair
            pair = Pair(team1, team2)
            for p in team1 + team2:
                p.current_pair = pair

            pending_scores[chat_id] = {'pair': pair, 'edit': True, 'edit_index': i, 'edit_round': round_num}

            await show_standings(chat_id, context)
            break


async def set_draw_round(chat_id, context, data):
    t = get_tournament(chat_id=chat_id)
    round_num = int(data.split("_")[-1])
    for i, r in enumerate(t.round_history):
        if r['round'] == round_num:
            # Rollback current stats
            team1_names = r["team1"]
            team2_names = r["team2"]
            team1 = [p for p in t.players if p.name in team1_names]
            team2 = [p for p in t.players if p.name in team2_names]
            score1, score2 = map(int, r['score'].split('-'))
            # Rollback
            if score1 == score2:
                for p in team1 + team2:
                    p.draws -= 1
                    p.points -= score1
            elif score1 > score2:
                for p in team1:
                    p.wins -= 1
                    p.points -= score1
                for p in team2:
                    p.losses -= 1
                    p.points -= score2
            else:
                for p in team1:
                    p.losses -= 1
                    p.points -= score1
                for p in team2:
                    p.wins -= 1
                    p.points -= score2
            # Set to draw
            half = t.round_points // 2
            for p in team1 + team2:
                p.draws += 1
                p.points += half
            r['score'] = f"{half}-{half}"
            t.round_history[i] = r
            await show_standings(chat_id, context)
            break


async def set_winner_team(chat_id, context, data):
    t = get_tournament(chat_id=chat_id)
    team = "team1" if "team1" in data else "team2"
    round_num = int(data.split("_")[-1])
    for i, r in enumerate(t.round_history):
        if r['round'] == round_num:
            team1_names = r["team1"]
            team2_names = r["team2"]
            team1 = [p for p in t.players if p.name in team1_names]
            team2 = [p for p in t.players if p.name in team2_names]
            winner_team = team1 if team == "team1" else team2
            # Rollback current
            score1, score2 = map(int, r['score'].split('-'))
            if score1 == score2:
                for p in team1 + team2:
                    p.draws -= 1
                    p.points -= score1
            elif score1 > score2:
                for p in team1:
                    p.wins -= 1
                    p.points -= score1
                for p in team2:
                    p.losses -= 1
                    p.points -= score2
            else:
                for p in team1:
                    p.losses -= 1
                    p.points -= score1
                for p in team2:
                    p.wins -= 1
                    p.points -= score2
            # Set pending for score
            pair = Pair(team1, team2)
            pending_scores[chat_id] = {'pair': pair, 'winner_team': winner_team, 'edit_index': i,
                                       'edit_round': round_num}
            await show_score_buttons(chat_id, context, winner_team)
            break


async def back_to_standings(chat_id, context):
    if chat_id in pending_edit_selection:
        del pending_edit_selection[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
    await show_standings(chat_id, context)
