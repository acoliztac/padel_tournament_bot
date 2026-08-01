from bot.state import pending_scores
from bot.utils.score_helpers import apply_win, apply_draw
from bot.utils.telegram_helpers import safe_edit_message_reply_markup, safe_delete_score_message
from bot.utils.tournaments_helpers import get_tournament


async def apply_result(chat_id, context, score):
    t = get_tournament(chat_id=chat_id)

    data = pending_scores[chat_id]

    pair = data['pair']
    is_edit = 'edit_index' in data

    # Draw
    if score is None:
        half = t.round_points // 2
        team1_score = half
        team2_score = half

        if not is_edit:
            for p in pair.team1 + pair.team2:
                p.games_played += 1

        apply_draw(
            pair.team1,
            pair.team2,
            half
        )

    # Win
    else:
        winner_team = data['winner_team']
        loser_team = [p for p in pair.team1 + pair.team2 if p not in winner_team]

        opponent_score = t.round_points - score

        if not is_edit:
            for p in pair.team1 + pair.team2:
                p.games_played += 1

        apply_win(
            winner_team,
            loser_team,
            score,
            opponent_score
        )

        if winner_team == pair.team1:
            team1_score = score
            team2_score = opponent_score
        else:
            team1_score = opponent_score
            team2_score = score

    pair.score = f"{team1_score}-{team2_score}"

    # Save history
    record = {
        "round": data.get('edit_round', t.current_round),
        "team1": [p.name for p in pair.team1],
        "team2": [p.name for p in pair.team2],
        "score": pair.score
    }

    if is_edit:
        t.round_history[data['edit_index']] = record
    else:
        t.round_history.append(record)

    # Cleanup
    await safe_delete_score_message(chat_id, context)

    del pending_scores[chat_id]

    if not is_edit:
        t.current_round += 1


async def apply_result_team(chat_id, context, data):
    pair = pending_scores[chat_id]['pair']
    winner_team = pair.team1 if data == "result_team1" else pair.team2
    pending_scores[chat_id]['winner_team'] = winner_team

    # Remove buttons from round message, keep the message
    if pending_scores[chat_id].get('round_msg_id'):
        await safe_edit_message_reply_markup(bot=context.bot, chat_id=chat_id,
                                             message_id=pending_scores[chat_id]['round_msg_id'], reply_markup=None)
    return winner_team
