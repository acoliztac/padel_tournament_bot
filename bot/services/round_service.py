from bot.state import pending_scores
from bot.utils.score_helpers import apply_win, apply_draw, rollback_match, rollback_match_result
from bot.utils.telegram_helpers import safe_edit_message_reply_markup, safe_delete_score_message
from bot.utils.tournaments_helpers import get_tournament


def prepare_round_edit(chat_id, round_num):
    tournament = get_tournament(chat_id=chat_id)

    for index, round_data in enumerate(tournament.round_history):
        if round_data["round"] != round_num:
            continue

        team1_names = round_data["team1"]
        team2_names = round_data["team2"]

        score1, score2 = map(int, round_data["score"].split("-"))

        players_by_name = {player.name: player for player in tournament.players}

        try:
            team1 = [players_by_name[name] for name in team1_names]
            team2 = [players_by_name[name] for name in team2_names]
        except KeyError:
            return False

        rollback_match(team1, team2, score1, score2)

        pair = tournament.create_pair(team1, team2)

        return {
            "pair": pair,
            "edit": True,
            "edit_index": index,
            "edit_round": round_num,
        }

    return True


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


def prepare_round_result_change(chat_id, round_num):
    """
    Находит завершённый раунд и откатывает его текущий результат.

    Возвращает данные раунда, необходимые для установки
    нового результата, или None, если раунд не найден.
    """

    tournament = get_tournament(chat_id=chat_id)

    players_by_name = {player.name: player for player in tournament.players}

    for index, round_data in enumerate(tournament.round_history):
        if round_data["round"] != round_num:
            continue

        try:
            team1 = [players_by_name[name] for name in round_data["team1"]]
            team2 = [players_by_name[name] for name in round_data["team2"]]
        except KeyError:
            return None

        score1, score2 = map(int, round_data["score"].split("-"), )

        rollback_match_result(team1=team1, team2=team2, score1=score1, score2=score2)

        return {
            "tournament": tournament,
            "index": index,
            "round_data": round_data,
            "team1": team1,
            "team2": team2,
        }

    return None


def set_round_draw_service(chat_id, round_num):
    """
    Изменяет результат завершённого раунда на ничью.
    """

    result_data = prepare_round_result_change(chat_id=chat_id, round_num=round_num, )

    if result_data is None:
        return False

    tournament = result_data["tournament"]
    index = result_data["index"]
    round_data = result_data["round_data"]

    team1 = result_data["team1"]
    team2 = result_data["team2"]

    half = tournament.round_points // 2

    apply_draw(team1=team1, team2=team2, points=half)

    round_data["score"] = f"{half}-{half}"
    tournament.round_history[index] = round_data

    return True


def prepare_round_winner_change(
        chat_id,
        round_num,
        winner_side,
):
    """
    Подготавливает завершённый раунд к выбору нового счёта.

    Старый результат откатывается.
    Новый результат будет применён позже через apply_result().
    """

    result_data = prepare_round_result_change(chat_id=chat_id, round_num=round_num,)

    if result_data is None:
        return None

    tournament = result_data["tournament"]
    index = result_data["index"]

    team1 = result_data["team1"]
    team2 = result_data["team2"]

    pair = tournament.create_pair(team1=team1, team2=team2,)

    winner_team = (team1 if winner_side == "team1" else team2)

    return {
        "pair": pair,
        "winner_team": winner_team,
        "edit": True,
        "edit_index": index,
        "edit_round": round_num,
    }
