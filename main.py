import os
import uuid
import random
import io
import csv
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import logging

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Add logging
# level DEBUG for more details, INFO for general info, WARNING for warnings, ERROR for errors
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

# Global player pool
players_pool = ["Никита", "Аннушка", "Денис", "Оля", "Дуэр", "Флоста"]

# -------------------- Analytics --------------------

def calculate_fair_table(tournament):
    """
    FAIR TABLE: Normalize all players to the minimum number of games.
    VALUE = P - O/2 (player's score - opponent's score/2)
    Remove least valuable matches until all have equal games.
    """
    if not tournament.round_history:
        return []
    
    # Create player data structure with all matches
    player_matches = {}
    for p in tournament.players:
        player_matches[p.name] = []
    
    # Collect all matches for each player
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score1, score2 = map(int, round_data["score"].split("-"))
        
        # Add match to both team members
        for player_name in team1:
            player_matches[player_name].append({
                "round": round_data["round"],
                "teammate": team1[0] if team1[0] != player_name else team1[1],
                "opponents": team2,
                "player_score": score1,
                "opponent_score": score2,
                "value": score1 - score2 / 2
            })
        
        for player_name in team2:
            player_matches[player_name].append({
                "round": round_data["round"],
                "teammate": team2[0] if team2[0] != player_name else team2[1],
                "opponents": team1,
                "player_score": score2,
                "opponent_score": score1,
                "value": score2 - score1 / 2
            })
    
    # Find minimum games played
    min_games = min(len(matches) for matches in player_matches.values()) if player_matches else 0
    
    # Calculate normalized stats
    normalized_stats = []
    for player_name, matches in player_matches.items():
        # Sort by value ascending (remove least valuable first)
        sorted_matches = sorted(matches, key=lambda m: m["value"])
        
        # Keep only min_games matches
        kept_matches = sorted_matches[len(sorted_matches) - min_games:] if len(sorted_matches) > min_games else sorted_matches
        
        total_points = sum(m["player_score"] for m in kept_matches)
        games = len(kept_matches)
        
        normalized_stats.append({
            "player": player_name,
            "games": games,
            "points": total_points
        })
    
    # Sort by points (descending) then player name
    normalized_stats.sort(key=lambda x: (-x["points"], x["player"]))
    
    return normalized_stats

def calculate_fun_table(tournament):
    """
    FUN TABLE: Measure "interestingness" of matches.
    fun per match = max(0, 10 - abs(score_diff))
    """
    if not tournament.round_history:
        return []
    
    player_fun = {}
    for p in tournament.players:
        player_fun[p.name] = 0
    
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score1, score2 = map(int, round_data["score"].split("-"))
        
        score_diff = abs(score1 - score2)
        fun_score = max(0, 10 - score_diff)
        
        # Add fun score to all players in the match
        for player_name in team1 + team2:
            player_fun[player_name] += fun_score
    
    # Create result list with place
    fun_stats = [
        {"player": name, "fun_score": score}
        for name, score in player_fun.items()
    ]
    
    # Sort by fun_score descending, then by player name for deterministic ordering
    fun_stats.sort(key=lambda x: (-x["fun_score"], x["player"]))
    
    return fun_stats

def get_raw_match_table(tournament):
    """
    RAW MATCH TABLE: Display all matches in order.
    """
    if not tournament.round_history:
        return []
    
    matches = []
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score = round_data["score"]
        
        matches.append({
            "round": round_data["round"],
            "team1": f"{team1[0]} & {team1[1]}",
            "score": score,
            "team2": f"{team2[0]} & {team2[1]}"
        })
    
    return matches

# -------------------- Classes --------------------

class Player:
    def __init__(self, name):
        self.name = name
        self.games_played = 0
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.points = 0
        self.current_pair = None

class Pair:
    def __init__(self, team1, team2):
        self.team1 = team1
        self.team2 = team2
        self.score = None

class Tournament:
    def __init__(self, name):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.players = []
        self.round = 1
        self.round_history = []
        self.stats_msg_id = None
        self.round_points = None

    def add_player(self, player):
        self.players.append(player)

    # -------------------- Mexicano 1+4 vs 2+3 --------------------
    def select_next_pair(self):
        if len(self.players) < 4:
            return None

        # 4 игрока с наименьшим количеством игр
        available_players = sorted(self.players, key=lambda p: (p.games_played, random.random()))
        selected = available_players[:4]

        # Сортируем по очкам: p1=max, p2>=p3, p4=min
        sorted_players = sorted(selected, key=lambda p: p.points, reverse=True)
        p1, p2, p3, p4 = sorted_players

        team1 = [p1, p4]
        team2 = [p2, p3]
        pair = Pair(team1, team2)
        for p in team1 + team2:
            p.current_pair = pair
        return pair

    def will_round_equalize_games(self, selected_players):
        # Проверяем, будут ли все игроки иметь одинаковое games_played после текущего раунда
        after_games = [p.games_played + (1 if p in selected_players else 0) for p in self.players]
        return len(set(after_games)) == 1

# -------------------- Storage --------------------

tournaments = {}
chat_tournaments = {}
pending_scores = {}
pending_new_player = {}
pending_player_selection = {}
pending_edit_selection = {}

# -------------------- Handlers --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_tournaments:
        await update.message.reply_text("Tournament already exists.")
        return
    
    pending_player_selection[chat_id] = {'selected': []}
    
    if not players_pool:
        await update.message.reply_text("No players in the list. Add a new player:")
        pending_new_player[chat_id] = True
        await context.bot.send_message(chat_id, "Enter player name:", reply_markup=ForceReply())
    else:
        await show_player_selection(update, context, chat_id)


async def show_player_selection(update, context, chat_id):
    selected = pending_player_selection[chat_id]['selected']
    
    keyboard = []
    for i, name in enumerate(players_pool):
        if name not in selected:
            keyboard.append([InlineKeyboardButton(f"✓ {name}", callback_data=f"select_player_{i}")])
        else:
            keyboard.append([InlineKeyboardButton(f"✗ {name}", callback_data=f"deselect_player_{i}")])
    
    keyboard.append([InlineKeyboardButton("Add new player", callback_data="add_new_player")])
    
    if len(selected) > 0:
        keyboard.append([InlineKeyboardButton("Delete selected", callback_data="delete_player")])
    
    if len(selected) >= 4:
        keyboard.append([InlineKeyboardButton("Start Tournament", callback_data="create_tournament")])
    
    msg_text = "Selected players:\n" + "\n".join(f"- {p}" for p in selected) if selected else "No players selected"
    
    if chat_tournaments.get(chat_id, {}).get('players_msg_id'):
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=chat_tournaments[chat_id]['players_msg_id'],
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.message:
        sent_msg = await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id
    else:
        sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id

async def show_tournament_mode(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    keyboard = [[InlineKeyboardButton("Finish Tournament", callback_data="finish_tournament")]]
    msg_text = "Tournament in progress..."
    
    if chat_tournaments[chat_id].get('tournament_msg_id'):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=chat_tournaments[chat_id]['tournament_msg_id'],
                text=msg_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
            chat_tournaments[chat_id]['tournament_msg_id'] = sent_msg.message_id
    else:
        sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        chat_tournaments[chat_id]['tournament_msg_id'] = sent_msg.message_id

async def show_points_selection(chat_id, context):
    keyboard = [[
        InlineKeyboardButton("16", callback_data="set_round_points_16"),
        InlineKeyboardButton("24", callback_data="set_round_points_24"),
        InlineKeyboardButton("32", callback_data="set_round_points_32")
    ]]
    sent = await context.bot.send_message(chat_id, "Select points per round:", reply_markup=InlineKeyboardMarkup(keyboard))
    chat_tournaments[chat_id]['points_msg_id'] = sent.message_id

async def show_score_buttons(chat_id, context, winner_team):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    half = t.round_points // 2
    buttons = [InlineKeyboardButton(str(i), callback_data=f"set_score_{i}") for i in range(half + 1, t.round_points + 1)]
    keyboard = [buttons[i:i+4] for i in range(0, len(buttons), 4)]  # 4 buttons per row
    msg_text = f"Winning team:\n{' & '.join(p.name for p in winner_team)}\nSelect score:"
    try:
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        pending_scores[chat_id]['score_msg_id'] = sent.message_id
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        pending_scores[chat_id]['score_msg_id'] = sent.message_id

# -------------------- Core --------------------

async def next_pair(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    
    pair = t.select_next_pair()
    if not pair:
        await context.bot.send_message(chat_id, "Waiting for 4 players...")
        await show_standings(chat_id, context)
        return
    pending_scores[chat_id] = {'pair': pair}
    await show_standings(chat_id, context)

# -------------------- Callbacks --------------------

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data == "create_tournament":
        selected = pending_player_selection.get(chat_id, {}).get('selected', [])
        if len(selected) < 4:
            await context.bot.send_message(chat_id, "Select at least 4 players!")
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
        
        await context.bot.send_message(chat_id, f"Tournament '{name}' created!\nPlayers:\n{"\n".join(f"- {p}" for p in selected)}")
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
        await context.bot.send_message(chat_id, "Enter player name:", reply_markup=ForceReply())
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
        if t.round > 1:
            # Откатить статистику последнего раунда
            last_round = t.round_history[-1]
            team1_names = last_round["team1"]
            team2_names = last_round["team2"]
            score_str = last_round["score"]
            team1_score, team2_score = map(int, score_str.split("-"))
            
            # Найти игроков
            team1 = [p for p in t.players if p.name in team1_names]
            team2 = [p for p in t.players if p.name in team2_names]
            
            # Откатить games_played
            for p in team1 + team2:
                p.games_played -= 1
            
            # Откатить wins, draws, losses, points
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
            
            # Создать pair из последнего раунда
            pair = Pair(team1, team2)
            for p in team1 + team2:
                p.current_pair = pair
            
            pending_scores[chat_id] = {'pair': pair, 'edit': True}
            
            # Удалить сообщения
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
            
            # Показать новые standings и edit pair
            await show_standings(chat_id, context)
            await next_pair(chat_id, context)
        else:
            await context.bot.send_message(chat_id, "No rounds to edit.")

    elif data.startswith("set_round_points_"):
        points = int(data.split("_")[-1])
        t.round_points = points
        # Delete points selection message
        if chat_tournaments[chat_id].get('points_msg_id'):
            try:
                await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['points_msg_id'])
            except:
                pass
        await context.bot.send_message(chat_id, f"Points per round set to {points}")
        await show_standings(chat_id, context)
        await next_pair(chat_id, context)

    elif data == "result_draw":
        pair = pending_scores[chat_id]['pair']
        half = t.round_points // 2
        pair.score = f"{half}-{half}"

        is_edit = 'edit_index' in pending_scores[chat_id]

        # Обновление статистики как draw
        for p in pair.team1 + pair.team2:
            if not is_edit:
                p.games_played += 1
            p.draws += 1
            p.points += half

        # Добавляем в историю
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
                "round": t.round,
                "team1": [p.name for p in pair.team1],
                "team2": [p.name for p in pair.team2],
                "score": pair.score
            })

        del pending_scores[chat_id]
        if not is_edit:
            t.round += 1
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

        # Обновление статистики: winner_team wins, other_team loses
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

        # Добавляем в историю
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
                "round": t.round,
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
            t.round += 1
        await show_standings(chat_id, context)
        await next_pair(chat_id, context)

    elif data.startswith("edit_round_"):
        round_num = int(data.split('_')[2])
        for i, r in enumerate(t.round_history):
            if r['round'] == round_num:
                # Откатить статистику
                team1_names = r["team1"]
                team2_names = r["team2"]
                score_str = r["score"]
                team1_score, team2_score = map(int, score_str.split("-"))
                
                # Найти игроков
                team1 = [p for p in t.players if p.name in team1_names]
                team2 = [p for p in t.players if p.name in team2_names]
                
                # Откатить games_played
                for p in team1 + team2:
                    p.games_played -= 1
                
                # Откатить wins, draws, losses, points
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
                
                # Создать pair
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
                pending_scores[chat_id] = {'pair': pair, 'winner_team': winner_team, 'edit_index': i, 'edit_round': round_num}
                await show_score_buttons(chat_id, context, winner_team)
                break

    elif data == "edit_rounds":
        pending_edit_selection[chat_id] = True
        await show_standings(chat_id, context)

    elif data == "back_to_standings":
        if chat_id in pending_edit_selection:
            del pending_edit_selection[chat_id]
        await show_standings(chat_id, context)

    elif data == "regenerate_pair":
        # Отменяем текущую pending пару, если она есть
        if chat_id in pending_scores:
            # Сбрасываем current_pair у игроков, чтобы они снова были доступны
            if 'pair' in pending_scores[chat_id]:
                for p in pending_scores[chat_id]['pair'].team1 + pending_scores[chat_id]['pair'].team2:
                    p.current_pair = None
            del pending_scores[chat_id]

        # Генерируем новую пару
        await next_pair(chat_id, context)
        return
# -------------------- Messages --------------------

async def handle_message(update, context):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()


    if chat_id in pending_new_player and pending_new_player[chat_id]:
        if text and text not in players_pool:
            players_pool.append(text)
        del pending_new_player[chat_id]
        await show_player_selection(update, context, chat_id)
        return

# -------------------- Standings --------------------

async def show_standings(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        lines.append(f"{i}. {p.name:<{max_name_len}} | Games: {p.games_played:<2} | W: {p.wins:<2} | D: {p.draws:<2} | L: {p.losses:<2} | Pts: {p.points:<3}")
    msg = "📊 Standings:\n<pre>\n" + "\n".join(lines) + "\n</pre>"

    # Add round history
    if t.round_history:
        msg += "\n\n📜 Round History:"
        for i, r in enumerate(t.round_history):
            team1_str = f"{r['team1'][0]} & {r['team1'][1]}"
            team2_str = f"{r['team2'][0]} & {r['team2'][1]}"
            score1, score2 = map(int, r['score'].split('-'))
            result = "Draw" if score1 == score2 else ("Team 1 Win" if score1 > score2 else "Team 2 Win")
            msg += f"\n\n🏓 Round {r['round']}\n🔹 {team1_str}\n\tvs\n🔸 {team2_str}\nScore: {r['score']}, {result}\n<code>────────────</code>"
            if i < len(t.round_history) - 1:
                msg += ""

    # Add current round if pending
    keyboard = []
    if chat_id in pending_scores:
        pair = pending_scores[chat_id]['pair']
        if pending_scores[chat_id].get('edit'):
            round_num = pending_scores[chat_id].get('edit_round', t.round - 1)
            msg_prefix = f"Edit Round {round_num}"
        else:
            round_num = t.round
            msg_prefix = f"🏓 Round {round_num}"
        equal_games = t.will_round_equalize_games(pair.team1 + pair.team2)
        equal_icon = "⚖️" if equal_games else ""
        msg += f"\n\n{msg_prefix}\n🔹 {pair.team1[0].name} & {pair.team1[1].name}\n\tvs\n🔸 {pair.team2[0].name} & {pair.team2[1].name}\n\nSelect result {equal_icon}:"
        keyboard = [[
            InlineKeyboardButton("Draw", callback_data="result_draw"),
            InlineKeyboardButton("Winner: 🔹 Team 1", callback_data="result_team1"),
            InlineKeyboardButton("Winner: 🔸 Team 2", callback_data="result_team2")
        ]]

    # Add regenerate button if pending
    keyboard.append([InlineKeyboardButton("🔄 Перегенерировать команды", callback_data="regenerate_pair")])

    # Add edit buttons
    if t.round_history:
        keyboard.append([InlineKeyboardButton("Edit Rounds", callback_data="edit_rounds")])

    if chat_id in pending_edit_selection:
        keyboard = []
        for r in t.round_history:
            keyboard.append([InlineKeyboardButton(f"Edit Round {r['round']}", callback_data=f"edit_round_{r['round']}")])
            keyboard.append([InlineKeyboardButton(f"Draw Round {r['round']}", callback_data=f"set_draw_round_{r['round']}"), InlineKeyboardButton(f"Winner: Team 1 Round {r['round']}", callback_data=f"set_winner_team1_round_{r['round']}"), InlineKeyboardButton(f"Winner: Team 2 Round {r['round']}", callback_data=f"set_winner_team2_round_{r['round']}")])
        keyboard.append([InlineKeyboardButton("Back to Standings", callback_data="back_to_standings")])

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except:
            try:
                await context.bot.delete_message(chat_id, t.stats_msg_id)
            except:
                pass
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
            t.stats_msg_id = sent.message_id
    else:
        sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        t.stats_msg_id = sent.message_id

# -------------------- Finalization & Export --------------------

async def finalize_tournament(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    # Delete score message
    if chat_id in pending_scores and pending_scores[chat_id].get('score_msg_id'):
        try:
            await context.bot.delete_message(chat_id, pending_scores[chat_id]['score_msg_id'])
        except:
            pass

    # Delete tournament mode message
    if chat_tournaments[chat_id].get('tournament_msg_id'):
        try:
            await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['tournament_msg_id'])
        except:
            pass

    # Delete round message
    if chat_tournaments[chat_id].get('round_msg_id'):
        try:
            await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['round_msg_id'])
        except:
            pass

    # Delete points selection message
    if chat_tournaments[chat_id].get('points_msg_id'):
        try:
            await context.bot.delete_message(chat_id, chat_tournaments[chat_id]['points_msg_id'])
        except:
            pass

    # Remove buttons from standings message
    if t.stats_msg_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=t.stats_msg_id, reply_markup=None)
        except:
            pass

    # Show final standings without buttons
    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        medal = "▫️"
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        lines.append(f"{medal} {i}. {p.name:<{max_name_len}} | Games: {p.games_played:<2} | W: {p.wins:<2} | D: {p.draws:<2} | L: {p.losses:<2} | Pts: {p.points:<3}")
    msg = "🏆 Tournament Finished!\n📊 Final Standings:\n<pre>\n" + "\n".join(lines) + "\n</pre>"
    
    # Add Fair Table (Normalized Games)
    fair_table = calculate_fair_table(t)
    fair_lines = []
    for i, entry in enumerate(fair_table, 1):
        medal = "▫️"
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        fair_lines.append(f"{medal} {i}. {entry['player']:<{max_name_len}} | Games: {entry['games']:<2} | Pts: {entry['points']:<3}")
    msg += "\n\n⚖️ Fair Table (Normalized Games):\n<pre>\n" + "\n".join(fair_lines) + "\n</pre>"
    
    # Add Fun Table (Match Interestingness)
    fun_table = calculate_fun_table(t)
    fun_lines = []
    for i, entry in enumerate(fun_table, 1):
        fun_lines.append(f"{i}. {entry['player']:<{max_name_len}} | Fun Score: {entry['fun_score']:<3}")
    msg += "\n\n🎉 Fun Table (Close Matches):\n<pre>\n" + "\n".join(fun_lines) + "\n</pre>"
    
    # Add Raw Match Table
    raw_matches = get_raw_match_table(t)
    matches_lines = []
    if raw_matches:
        max_team_len = max(len(m['team1']) for m in raw_matches)
        for match in raw_matches:
            matches_lines.append(f"R{match['round']} | {match['team1']:<{max_team_len}} | {match['score']:<5} | {match['team2']}")
        msg += "\n\n📜 Match History:\n<pre>\n" + "\n".join(matches_lines) + "\n</pre>"
    
    if t.stats_msg_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    # --- Export CSV for backup ---
    # History
    history_csv = io.StringIO()
    writer = csv.writer(history_csv)
    writer.writerow(["Round","Team1","Team2","Score"])
    for r in t.round_history:
        writer.writerow([r["round"], ",".join(r["team1"]), ",".join(r["team2"]), r["score"]])
    history_csv.seek(0)
    await context.bot.send_document(chat_id, document=history_csv, filename=f"{t.name}_history.csv")

    # Player Summary
    summary_csv = io.StringIO()
    writer = csv.writer(summary_csv)
    writer.writerow(["Player","Games","Wins","Draws","Losses","Points"])
    for p in t.players:
        writer.writerow([p.name, p.games_played, p.wins, p.draws, p.losses, p.points])
    summary_csv.seek(0)
    await context.bot.send_document(chat_id, document=summary_csv, filename=f"{t.name}_summary.csv")

    # Clear old tournament
    t_id = t.id
    del tournaments[t_id]
    del chat_tournaments[chat_id]
    if chat_id in pending_scores:
        del pending_scores[chat_id]

    # --- Start new tournament button ---
    keyboard = [[InlineKeyboardButton("Start New Tournament", callback_data="start_new_tournament")]]
    await context.bot.send_message(chat_id, "Start a new tournament?", reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------- Run --------------------

async def error_handler(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    if update and update.effective_chat:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred. Please try again.")
        except RetryAfter:
            pass  # Avoid sending message if flood control is active

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
