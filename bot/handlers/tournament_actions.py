import asyncio
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import RetryAfter

from bot.handlers.common import (
    add_final_table,
    add_raw_match_table,
    add_best_worst_partners_table,
    add_fun_table,
    add_tense_matches_table,
    add_fair_table,
    remove_buttons_from_standings_message,
    delete_points_selection_message,
    delete_round_message,
    delete_tournament_mode_message,
    delete_score_message,
    show_standings,
    show_points_selection,
    show_tournament_mode, show_player_selection, show_score_buttons
)
from bot.state import (
    anti_spam_msg_ids,
    pending_edit_selection,
    pending_manual_pair,
    pending_scores,
    chat_tournaments,
    tournaments,
    pending_player_selection, pending_new_player, players_pool, pending_management, pending_regenerate_menu
)
from bot.tournament import Tournament, Player, Pair


async def next_pair(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]

    pair = t.select_next_pair()
    if not pair:
        await context.bot.send_message(chat_id, "Ожидание 4 игроков...")
        await show_standings(chat_id, context)
        return
    pending_scores[chat_id] = {'pair': pair}
    await show_standings(chat_id, context)


async def finalize_tournament(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML")
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
        try:
            await context.bot.delete_message(chat_id, players_msg_id)
        except:
            pass

    if chat_id in pending_player_selection:
        del pending_player_selection[chat_id]

    await show_tournament_mode(chat_id, context)
    await show_points_selection(chat_id, context)


async def start_new_tournament(chat_id, query, context):
    pending_player_selection[chat_id] = {'selected': []}
    await show_player_selection(query, context, chat_id)
    await context.bot.delete_message(chat_id, query.message.message_id)
    return


async def add_new_player(chat_id, context):
    pending_new_player[chat_id] = True
    await context.bot.send_message(chat_id, "Введите имя игрока:", reply_markup=ForceReply())


async def select_all_players(chat_id, query, context):
    pending_player_selection[chat_id]['selected'] = list(players_pool)
    await show_player_selection(query, context, chat_id)


async def delete_player(chat_id, query, context):
    selected = pending_player_selection[chat_id]['selected']
    for name in selected:
        if name in players_pool:
            players_pool.remove(name)
    pending_player_selection[chat_id]['selected'] = []
    await show_player_selection(query, context, chat_id)


async def confirm_delete(chat_id, query, context, data):
    name = data.split("confirm_delete_")[1]
    pending_player_selection[chat_id]['selected'].remove(name)
    if name in players_pool:
        players_pool.remove(name)
    await show_player_selection(query, context, chat_id)


async def select_player(chat_id, context, query, data):
    idx = int(data.split("_")[2])
    if idx < len(players_pool):
        pending_player_selection[chat_id]['selected'].append(players_pool[idx])
        await show_player_selection(query, context, chat_id)


async def deselect_player(chat_id, data, query, context):
    idx = int(data.split("_")[2])
    if idx < len(players_pool):
        pending_player_selection[chat_id]['selected'].remove(players_pool[idx])
        await show_player_selection(query, context, chat_id)


async def edit_last_round(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def set_round_points(chat_id, data, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def result_draw(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=pending_scores[chat_id]['round_msg_id'],
                reply_markup=None
            )
        except:
            pass

    await show_score_buttons(chat_id, context, winner_team)


async def set_score(chat_id, data, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def cancel_manual_pair(chat_id, context):
    del pending_manual_pair[chat_id]
    await show_standings(chat_id, context)
    return


async def reset_manual_pair(chat_id, context):
    pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
    await show_standings(chat_id, context)
    return


async def confirm_manual_pair(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def remove_from_team(chat_id, context, data):
    player = data.split("remove_from_team_", 1)[1]
    if player in pending_manual_pair[chat_id]['team1']:
        pending_manual_pair[chat_id]['team1'].remove(player)
    elif player in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team2'].remove(player)
    await show_standings(chat_id, context)
    return


async def add_to_team2(chat_id, context, data):
    player = data.split("add_to_team2_", 1)[1]
    if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team2'].append(player)
    await show_standings(chat_id, context)
    return


async def add_to_team1(chat_id, context, data):
    player = data.split("add_to_team1_", 1)[1]
    if player not in pending_manual_pair[chat_id]['team1'] and player not in pending_manual_pair[chat_id]['team2']:
        pending_manual_pair[chat_id]['team1'].append(player)
    await show_standings(chat_id, context)
    return


async def regenerate_manual(chat_id, context):
    if chat_id in pending_regenerate_menu:
        del pending_regenerate_menu[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
    pending_manual_pair[chat_id] = {'team1': [], 'team2': []}
    await show_standings(chat_id, context)
    return


async def regenerate_auto(chat_id, context):
    if chat_id in pending_regenerate_menu:
        del pending_regenerate_menu[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
    if chat_id in pending_scores:
        del pending_scores[chat_id]
    await next_pair(chat_id, context)
    return


async def management(chat_id, context):
    pending_management[chat_id] = True
    await show_standings(chat_id, context)


async def edit_rounds(chat_id, context):
    pending_edit_selection[chat_id] = True
    await show_standings(chat_id, context)


async def back_to_standings(chat_id, context):
    if chat_id in pending_edit_selection:
        del pending_edit_selection[chat_id]
    if chat_id in pending_management:
        del pending_management[chat_id]
    await show_standings(chat_id, context)


async def set_winner_team(chat_id, context, data):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def set_draw_round(chat_id, context, data):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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


async def edit_round(chat_id, context, data):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
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
