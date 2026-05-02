import os
import uuid
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import logging

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Configure logging
# level DEBUG for more details, INFO for general info, WARNING for warnings, ERROR for errors
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

# Global player pool
players_pool = ["Никита", "Аннушка", "Денис", "Оля", "Дуэр", "Флоста"]

# Global dict for anti-spam message IDs
anti_spam_msg_ids = {}

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
    Divided by number of games played to get average fun score per game.
    """
    if not tournament.round_history:
        return []
    
    player_fun = {}
    player_games = {}
    for p in tournament.players:
        player_fun[p.name] = 0
        player_games[p.name] = 0
    
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score1, score2 = map(int, round_data["score"].split("-"))
        
        score_diff = abs(score1 - score2)
        fun_score = max(0, 10 - score_diff)
        
        # Add fun score to all players in the match
        for player_name in team1 + team2:
            player_fun[player_name] += fun_score
            player_games[player_name] += 1
    
    # Create result list with average fun score per game
    fun_stats = []
    for name in player_fun.keys():
        avg_fun = player_fun[name] / player_games[name] if player_games[name] > 0 else 0
        fun_stats.append({
            "player": name,
            "fun_score": round(avg_fun, 2),
            "total_fun": player_fun[name],
            "games": player_games[name]
        })
    
    # Sort by average fun_score descending, then by player name for deterministic ordering
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

        # 4 players with the least number of games
        available_players = sorted(self.players, key=lambda p: (p.games_played, random.random()))
        selected = available_players[:4]

        # Sort by points: p1=max, p2>=p3, p4=min
        sorted_players = sorted(selected, key=lambda p: p.points, reverse=True)
        p1, p2, p3, p4 = sorted_players

        team1 = [p1, p4]
        team2 = [p2, p3]
        pair = Pair(team1, team2)
        for p in team1 + team2:
            p.current_pair = pair
        return pair

    def will_round_equalize_games(self, selected_players):
        # Check if all players will have the same games_played after the current round
        after_games = [p.games_played + (1 if p in selected_players else 0) for p in self.players]
        return len(set(after_games)) == 1

# -------------------- Storage --------------------

tournaments = {}
chat_tournaments = {}
pending_scores = {}
pending_new_player = {}
pending_player_selection = {}
pending_edit_selection = {}
pending_manual_pair = {}
pending_regenerate_menu = {}

# -------------------- Handlers --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_tournaments:
        await show_tournament_mode(chat_id, context)
        try:
            await context.bot.delete_message(chat_id, update.message.message_id)
        except:
            pass
        return
    
    pending_player_selection[chat_id] = {'selected': []}
    
    if not players_pool:
        await update.message.reply_text("В списке нет игроков. Добавьте нового игрока:")
        pending_new_player[chat_id] = True
        await context.bot.send_message(chat_id, "Введите имя игрока:", reply_markup=ForceReply())
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
    
    keyboard.append([InlineKeyboardButton("Добавить нового игрока", callback_data="add_new_player")])

    if len(selected) < len(players_pool):
        keyboard.append([InlineKeyboardButton("Выбрать всех", callback_data="select_all_players")])

    if len(selected) > 0:
        keyboard.append([InlineKeyboardButton("Удалить выбранных", callback_data="delete_player")])
    
    if len(selected) >= 4:
        keyboard.append([InlineKeyboardButton("Начать турнир", callback_data="create_tournament")])
    
    msg_text = "В турнире принимают участие:\n" + "\n".join(f"- {p}" for p in selected) if selected else "Игроки не выбраны"
    
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
    keyboard = [[InlineKeyboardButton("Завершить турнир", callback_data="finish_tournament")]]
    msg_text = "Турнир в процессе..."
    
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
    sent = await context.bot.send_message(chat_id, "Выберите количество очков за раунд:", reply_markup=InlineKeyboardMarkup(keyboard))
    chat_tournaments[chat_id]['points_msg_id'] = sent.message_id

async def show_score_buttons(chat_id, context, winner_team):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    half = t.round_points // 2
    buttons = [InlineKeyboardButton(str(i), callback_data=f"set_score_{i}") for i in range(half + 1, t.round_points + 1)]
    keyboard = [buttons[i:i+4] for i in range(0, len(buttons), 4)]  # 4 buttons per row
    msg_text = f"Выигравшая команда:\n{' & '.join(p.name for p in winner_team)}\nВыберите счёт:"
    try:
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        pending_scores[chat_id]['score_msg_id'] = sent.message_id
    except RetryAfter as e:
        try:
            sent_anti = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
            anti_spam_msg_ids[chat_id] = sent_anti.message_id
        except:
            pass
        await asyncio.sleep(e.retry_after)
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        pending_scores[chat_id]['score_msg_id'] = sent.message_id

# -------------------- Core --------------------

async def next_pair(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    
    pair = t.select_next_pair()
    if not pair:
        await context.bot.send_message(chat_id, "Ожидание 4 игроков...")
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
        
        await context.bot.send_message(chat_id, f"Турнир '{name}' создан!\nИгроки:\n{"\n".join(f"- {p}" for p in selected)}")
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
        if t.round > 1:
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
        await context.bot.send_message(chat_id, f"Очки за раунд установлены на {points}")
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
                pending_scores[chat_id] = {'pair': pair, 'winner_team': winner_team, 'edit_index': i, 'edit_round': round_num}
                await show_score_buttons(chat_id, context, winner_team)
                break

    elif data == "back_to_standings":
        if chat_id in pending_edit_selection:
            del pending_edit_selection[chat_id]
        await show_standings(chat_id, context)

    elif data == "regenerate_auto":
        if chat_id in pending_regenerate_menu:
            del pending_regenerate_menu[chat_id]
        if chat_id in pending_scores:
            del pending_scores[chat_id]
        await next_pair(chat_id, context)
        return

    elif data == "regenerate_manual":
        if chat_id in pending_regenerate_menu:
            del pending_regenerate_menu[chat_id]
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
    if chat_id in anti_spam_msg_ids:
        try:
            await context.bot.delete_message(chat_id, anti_spam_msg_ids[chat_id])
        except:
            pass
        del anti_spam_msg_ids[chat_id]
    
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        lines.append(f"{i}. {p.name:<{max_name_len}} | Игры: {p.games_played:<2} | П: {p.wins:<2} | Н: {p.draws:<2} | Пр: {p.losses:<2} | Оч: {p.points:<3}")
    msg = "📊 Турнирная таблица:\n<pre>\n" + "\n".join(lines) + "\n</pre>"

    # Add round history
    if t.round_history:
        msg += "\n\n📜 История раундов:"
        for i, r in enumerate(t.round_history):
            team1_str = f"{r['team1'][0]} & {r['team1'][1]}"
            team2_str = f"{r['team2'][0]} & {r['team2'][1]}"
            score1, score2 = map(int, r['score'].split('-'))
            result = "Ничья" if score1 == score2 else ("Победа команды 🔹" if score1 > score2 else "Победа команды 🔸")
            msg += f"\n\n🏓 Раунд {r['round']}\n🔹 {team1_str}\n\tvs\n🔸 {team2_str}\nСчёт: {r['score']}, {result}\n<code>────────────────────────</code>"
            if i < len(t.round_history) - 1:
                msg += ""

    # Add current round if pending
    keyboard = []
    if chat_id in pending_scores:
        pair = pending_scores[chat_id]['pair']
        if pending_scores[chat_id].get('edit'):
            round_num = pending_scores[chat_id].get('edit_round', t.round - 1)
            msg_prefix = f"Редактировать раунд {round_num}"
        else:
            round_num = t.round
            msg_prefix = f"🏓 Раунд {round_num}"
        equal_games = t.will_round_equalize_games(pair.team1 + pair.team2)
        equal_icon = "⚖️" if equal_games else ""
        msg += f"\n\n{msg_prefix}\n🔹 {pair.team1[0].name} & {pair.team1[1].name}\n\tvs\n🔸 {pair.team2[0].name} & {pair.team2[1].name}\n\nВыберите победителя {equal_icon}:"
        keyboard = [[
            InlineKeyboardButton("Ничья", callback_data="result_draw"),
            InlineKeyboardButton("Победитель: 🔹 ", callback_data="result_team1"),
            InlineKeyboardButton("Победитель: 🔸 ", callback_data="result_team2")
        ]]

    # Add regenerate button if pending
    keyboard.append([
        InlineKeyboardButton("🔄 Перегенерировать команды", callback_data="regenerate_auto"),
        InlineKeyboardButton("👉 Ручная генерация команд", callback_data="regenerate_manual")
    ])

    if chat_id in pending_edit_selection:
        keyboard = []
        for r in t.round_history:
            keyboard.append([InlineKeyboardButton(f"Редактировать раунд {r['round']}", callback_data=f"edit_round_{r['round']}")])
            keyboard.append([InlineKeyboardButton(f"Ничья", callback_data=f"set_draw_round_{r['round']}"), InlineKeyboardButton(f"Победитель: Победитель: 🔹 ", callback_data=f"set_winner_team1_round_{r['round']}"), InlineKeyboardButton(f"Победитель: 🔸 ", callback_data=f"set_winner_team2_round_{r['round']}")])
        keyboard.append([InlineKeyboardButton("Вернуться к таблице", callback_data="back_to_standings")])

    if chat_id in pending_manual_pair:
        team1 = pending_manual_pair[chat_id]['team1']
        team2 = pending_manual_pair[chat_id]['team2']
        round_num = t.round
        msg = f"Ручная генерация команд для Раунда {round_num}:\n"
        msg += f"Команда 1: {', '.join(team1) if team1 else 'Пусто'}\n"
        msg += f"Команда 2: {', '.join(team2) if team2 else 'Пусто'}\n\n"
        msg += "Выберите игроков:"
        keyboard = []
        available_players = [p.name for p in t.players if p.name not in team1 and p.name not in team2]
        for player in available_players:
            keyboard.append([
                InlineKeyboardButton(f"➕ В Команду 1: {player}", callback_data=f"add_to_team1_{player}"),
                InlineKeyboardButton(f"➕ В Команду 2: {player}", callback_data=f"add_to_team2_{player}")
            ])
        # Кнопки для удаления
        for player in team1 + team2:
            team = "1" if player in team1 else "2"
            keyboard.append([InlineKeyboardButton(f"➖ Удалить {player} из Команды {team}", callback_data=f"remove_from_team_{player}")])
        # Кнопки действий
        keyboard.append([
            InlineKeyboardButton("✅ Подтвердить команды", callback_data="confirm_manual_pair"),
            InlineKeyboardButton("🔄 Сбросить", callback_data="reset_manual_pair"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_pair")
        ])
        # Отправить или редактировать сообщение
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            sent = await context.bot.send_message(chat_id, msg, reply_markup=InlineKeyboardMarkup(keyboard))
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except RetryAfter as e:
            try:
                sent = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
                anti_spam_msg_ids[chat_id] = sent.message_id
            except:
                pass
            await asyncio.sleep(e.retry_after)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except:
            try:
                await context.bot.delete_message(chat_id, t.stats_msg_id)
            except:
                pass
            try:
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
            t.stats_msg_id = sent.message_id
    else:
        try:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
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
        lines.append(f"{medal} {i}. {p.name:<{max_name_len}} | Игры: {p.games_played:<2} | П: {p.wins:<2} | Н: {p.draws:<2} | Пр: {p.losses:<2} | Оч: {p.points:<3}")
    msg = "🏆 Турнир завершён!\n📊 Финальные результаты:\n<pre>\n" + "\n".join(lines) + "\n</pre>"
    
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
        fair_lines.append(f"{medal} {i}. {entry['player']:<{max_name_len}} | Игры: {entry['games']:<2} | Оч: {entry['points']:<3}")
    msg += "\n\n⚖️ Справедливые результаты (с учётом равенства игр):\n<pre>\n" + "\n".join(fair_lines) + "\n</pre>"
    
    # Add Fun Table (Match Interestingness)
    fun_table = calculate_fun_table(t)
    fun_lines = []
    for i, entry in enumerate(fun_table, 1):
        fun_lines.append(f"{i}. {entry['player']:<{max_name_len}} | Средн. интерес: {entry['fun_score']:<5} | Игры: {entry['games']:<2}")
    msg += "\n\n🎉 Самые фаново играющие:\n<pre>\n" + "\n".join(fun_lines) + "\n</pre>"
    
    # Add Raw Match Table
    raw_matches = get_raw_match_table(t)
    matches_lines = []
    if raw_matches:
        max_team_len = max(len(m['team1']) for m in raw_matches)
        for match in raw_matches:
            matches_lines.append(f"R{match['round']:3} | {match['team1']:<{max_team_len}} | {match['score']:<5} | {match['team2']}")
        msg += "\n\n📜 История раундов:\n<pre>\n" + "\n".join(matches_lines) + "\n</pre>"
    
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

# -------------------- Run --------------------

async def error_handler(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    if update and update.effective_chat:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка. Пожалуйста, попробуйте снова.")
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
