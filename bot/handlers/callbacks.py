from datetime import datetime

from telegram import ForceReply

from bot.state import (
    tournaments,
    chat_tournaments,
    pending_scores,
    pending_new_player,
    pending_player_selection,
    pending_edit_selection,
    pending_manual_pair,
    pending_regenerate_menu,
    pending_management,
    players_pool
)
from bot.tournament import Pair, Player, Tournament
from bot.handlers.common import (
    show_standings,
    next_pair,
    show_score_buttons,
    show_player_selection,
    finalize_tournament,
    show_tournament_mode,
    show_points_selection
)


async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data == "create_tournament":
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
            try:
                await context.bot.delete_message(chat_id, players_msg_id)
            except:
                pass

        if chat_id in pending_player_selection:
            del pending_player_selection[chat_id]

        await show_tournament_mode(chat_id, context)
        await show_points_selection(chat_id, context)
        return

    if data == "start_new_tournament":
        pending_player_selection[chat_id] = {'selected': []}
        await show_player_selection(query, context, chat_id)
        await context.bot.delete_message(chat_id, query.message.message_id)
        return

    if data == "add_new_player":
        pending_new_player[chat_id] = True
        await context.bot.send_message(chat_id, "Введите имя игрока:", reply_markup=ForceReply())
        return

    if data == "select_all_players":
        pending_player_selection[chat_id]['selected'] = list(players_pool)
        await show_player_selection(query, context, chat_id)
        return

    if data == "delete_player":
        selected = pending_player_selection[chat_id]['selected']
        for name in selected:
            if name in players_pool:
                players_pool.remove(name)
        pending_player_selection[chat_id]['selected'] = []
        await show_player_selection(query, context, chat_id)
        return

    if data.startswith("confirm_delete_"):
        name = data.split("confirm_delete_")[1]
        pending_player_selection[chat_id]['selected'].remove(name)
        if name in players_pool:
            players_pool.remove(name)
        await show_player_selection(query, context, chat_id)
        return

    if data == "back_to_selection":
        await show_player_selection(query, context, chat_id)
        return

    if data.startswith("select_player_"):
        idx = int(data.split("_")[2])
        if idx < len(players_pool):
            pending_player_selection[chat_id]['selected'].append(players_pool[idx])
            await show_player_selection(query, context, chat_id)
        return

    if data.startswith("deselect_player_"):
        idx = int(data.split("_")[2])
        if idx < len(players_pool):
            pending_player_selection[chat_id]['selected'].remove(players_pool[idx])
            await show_player_selection(query, context, chat_id)
        return

    if chat_id not in chat_tournaments:
        return

    t = tournaments[chat_tournaments[chat_id]['t_id']]

    if data == "finish_tournament":
        await finalize_tournament(chat_id, context)

    elif data == "edit_last_round":
        if t.current_round > 1:
            # Rollback last round statistics
            last_round = t.round_history[-1]
            team1_names = last_round["team1"]
            team2_names = last_round["team2"]
            score_str = last_round["score"]
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

            # Create pair from last round
            pair = Pair(team1, team2)
            for p in team1 + team2:
                p.current_pair = pair

            pending_scores[chat_id] = {'pair': pair, 'edit': True}

            # Delete messages
            if t.stats_msg_id:
                try:
                    await context.bot.delete_message(chat_id, t.stats_msg_id)
                except:
                    pass
                t.stats_msg_id = None

            if chat_tournaments[chat_id].get('round_msg_id'):
                try:
                    await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['round_msg_id'])
                except:
                    pass
                del chat_tournaments[chat_id]['round_msg_id']

            # Show new standings and edit pair
            await show_standings(chat_id, context)
            await next_pair(chat_id, context)
        else:
            await context.bot.send_message(chat_id, "Нет раундов для редактирования.")

    elif data.startswith("set_round_points_"):
        points = int(data.split("_")[-1])
        t.round_points = points
        # Delete points selection message
        if chat_tournaments[chat_id].get('points_msg_id'):
            try:
                await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['points_msg_id'])
            except:
                pass
        await show_standings(chat_id, context)
        await next_pair(chat_id, context)

    elif data == "result_draw":
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

    elif data in ["result_team1", "result_team2"]:
        pair = pending_scores[chat_id]['pair']
        winner_team = pair.team1 if data == "result_team1" else pair.team2
        pending_scores[chat_id]['winner_team'] = winner_team

        # Remove buttons from round message, keep the message
        if pending_scores[chat_id].get('round_msg_id'):
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=pending_scores[chat_id]['round_msg_id'],
                    reply_markup=None
                )
            except:
                pass

        await show_score_buttons(chat_id, context, winner_team)

    elif data.startswith("set_score_"):
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
            try:
                await context.bot.delete_message(chat_id, pending_scores[chat_id]['score_msg_id'])
            except:
                pass

        del pending_scores[chat_id]
        if not is_edit:
            t.current_round += 1
        await show_standings(chat_id, context)
        await next_pair(chat_id, context)

    elif data.startswith("edit_round_"):
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

    elif data.startswith("set_draw_round_"):
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

    elif data.startswith("set_winner_team1_round_") or data.startswith("set_winner_team2_round_"):
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

    elif data == "back_to_standings":
        if chat_id in pending_edit_selection:
            del pending_edit_selection[chat_id]
        if chat_id in pending_management:
            del pending_management[chat_id]
        await show_standings(chat_id, context)

    elif data == "edit_rounds":
        pending_edit_selection[chat_id] = True
        await show_standings(chat_id, context)

    elif data == "management":
        pending_management[chat_id] = True
        await show_standings(chat_id, context)

    elif data == "regenerate_auto":
        if chat_id in pending_regenerate_menu:
            del pending_regenerate_menu[chat_id]
        if chat_id in pending_management:
            del pending_management[chat_id]
        if chat_id in pending_scores:
            del pending_scores[chat_id]
        await next_pair(chat_id, context)
        return

    elif data == "regenerate_manual":
        if chat_id in pending_regenerate_menu:
            del pending_regenerate_menu[chat_id]
        if chat_id in pending_management:
            del pending_management[chat_id]
        pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
        await show_standings(chat_id, context)
        return

    elif data.startswith("add_to_team1_"):
        player = data.split("add_to_team1_", 1)[1]
        if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
            pending_manual_pair[chat_id]['team1'].append(player)
        await show_standings(chat_id, context)
        return

    elif data.startswith("add_to_team2_"):
        player = data.split("add_to_team2_", 1)[1]
        if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
            pending_manual_pair[chat_id]['team2'].append(player)
        await show_standings(chat_id, context)
        return

    elif data.startswith("remove_from_team_"):
        player = data.split("remove_from_team_", 1)[1]
        if player in pending_manual_pair[chat_id]['team1']:
            pending_manual_pair[chat_id]['team1'].remove(player)
        elif player in pending_manual_pair[chat_id]['team2']:
            pending_manual_pair[chat_id]['team2'].remove(player)
        await show_standings(chat_id, context)
        return

    elif data == "confirm_manual_pair":
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

    elif data == "reset_manual_pair":
        pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
        await show_standings(chat_id, context)
        return

    elif data == "cancel_manual_pair":
        del pending_manual_pair[chat_id]
        await show_standings(chat_id, context)
        return
