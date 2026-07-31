from bot.handlers.actions.tournament_actions import next_pair
from bot.handlers.common import show_standings, show_score_buttons
from bot.state import pending_scores
from bot.utils.telegram_helpers import safe_edit_message_reply_markup, safe_delete_message
from bot.utils.tournaments_helpers import get_tournament


async def set_score(chat_id, data, context):
    t = get_tournament(chat_id=chat_id)
    score = int(data.split("_")[-1])
    pair = pending_scores[chat_id]['pair']
    winner_team = pending_scores[chat_id]['winner_team']
    other_team = [p for p in pair.team1 + pair.team2 if p not in winner_team]

    opponent_score = t.round_points - score

    is_edit = 'edit_index' in pending_scores[chat_id]

    # Update statistics: winner_team wins, other_team loses
    for p in pair.team1 + pair.team2:
        if not is_edit:
            p.games_played += 1

    for p in winner_team:
        p.wins += 1
        p.points += score
    for p in other_team:
        p.losses += 1
        p.points += opponent_score

    # Set score in team1 - team2 order
    if winner_team == pair.team1:
        team1_score = score
        team2_score = opponent_score
    else:
        team1_score = opponent_score
        team2_score = score
    pair.score = f"{team1_score}-{team2_score}"

    # Add to history
    if is_edit:
        idx = pending_scores[chat_id]['edit_index']
        round_num = pending_scores[chat_id]['edit_round']
        t.round_history[idx] = {
            "round": round_num,
            "team1": [p.name for p in pair.team1],
            "team2": [p.name for p in pair.team2],
            "score": pair.score
        }
    else:
        t.round_history.append({
            "round": t.current_round,
            "team1": [p.name for p in pair.team1],
            "team2": [p.name for p in pair.team2],
            "score": pair.score
        })

    # Delete score message
    if pending_scores[chat_id].get('score_msg_id'):
        await safe_delete_message(context.bot, chat_id, pending_scores[chat_id]['score_msg_id'])

    del pending_scores[chat_id]
    if not is_edit:
        t.current_round += 1
    await show_standings(chat_id, context)
    await next_pair(chat_id, context)


async def result_draw(chat_id, context):
    t = get_tournament(chat_id=chat_id)
    pair = pending_scores[chat_id]['pair']
    half = t.round_points // 2
    pair.score = f"{half}-{half}"

    is_edit = 'edit_index' in pending_scores[chat_id]

    # Update statistics as draw
    for p in pair.team1 + pair.team2:
        if not is_edit:
            p.games_played += 1
        p.draws += 1
        p.points += half

    # Add to history
    if is_edit:
        idx = pending_scores[chat_id]['edit_index']
        round_num = pending_scores[chat_id]['edit_round']
        t.round_history[idx] = {
            "round": round_num,
            "team1": [p.name for p in pair.team1],
            "team2": [p.name for p in pair.team2],
            "score": pair.score
        }
    else:
        t.round_history.append({
            "round": t.current_round,
            "team1": [p.name for p in pair.team1],
            "team2": [p.name for p in pair.team2],
            "score": pair.score
        })

    del pending_scores[chat_id]
    if not is_edit:
        t.current_round += 1
    await show_standings(chat_id, context)
    await next_pair(chat_id, context)


async def result_team(chat_id, data, context):
    pair = pending_scores[chat_id]['pair']
    winner_team = pair.team1 if data == "result_team1" else pair.team2
    pending_scores[chat_id]['winner_team'] = winner_team

    # Remove buttons from round message, keep the message
    if pending_scores[chat_id].get('round_msg_id'):
        await safe_edit_message_reply_markup(bot=context.bot, chat_id=chat_id,
                                             message_id=pending_scores[chat_id]['round_msg_id'], reply_markup=None)

    await show_score_buttons(chat_id, context, winner_team)
