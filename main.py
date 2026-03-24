import os
import uuid
import random
import io
import csv
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import logging

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Add logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global player pool
players_pool = ["Никита", "Аннушка", "Денис", "Оля", "Дуэр", "Флоста"]

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
        available_players = sorted(self.players, key=lambda p: (p.games_played, -p.points, random.random()))
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
pending_round_points = {}
pending_new_player = {}
pending_player_selection = {}
pending_tournament_name = {}

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
    msg_text = "Tournament in progress...\n" + "\n".join(f"- {p.name}" for p in t.players)
    
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

# -------------------- Core --------------------

async def next_pair(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    pair = t.select_next_pair()
    if not pair:
        await context.bot.send_message(chat_id, "Waiting for 4 players...")
        return

    pending_scores[chat_id] = {'pair': pair}

    # Индикатор равного количества игр после этого раунда
    equal_games = t.will_round_equalize_games(pair.team1 + pair.team2)
    equal_icon = "⚖️" if equal_games else ""

    msg_text = f"🏓 Round {t.round} {equal_icon}\n" \
               f"{pair.team1[0].name} & {pair.team1[1].name}\nvs\n" \
               f"{pair.team2[0].name} & {pair.team2[1].name}\n\n" \
               f"Select team and enter its score:"

    keyboard = [[
        InlineKeyboardButton("Team 1", callback_data="score_team1"),
        InlineKeyboardButton("Team 2", callback_data="score_team2")
    ]]

    sent = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
    pending_scores[chat_id]['round_msg_id'] = sent.message_id
    chat_tournaments[chat_id]['round_msg_id'] = sent.message_id

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
        
        # Store selected players for later
        pending_tournament_name[chat_id] = selected
        
        # Delete player selection message
        players_msg_id = chat_tournaments.get(chat_id, {}).get('players_msg_id')
        if players_msg_id:
            try:
                await context.bot.delete_message(chat_id, players_msg_id)
            except:
                pass
        
        if chat_id in pending_player_selection:
            del pending_player_selection[chat_id]
        
        await context.bot.send_message(chat_id, "Enter tournament name:", reply_markup=ForceReply())
        return

    if data == "start_new_tournament":
        pending_player_selection[chat_id] = {'selected': []}
        await show_player_selection(query, context, chat_id)
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

    if data == "start_round":
        if t.round_points is None:
            pending_round_points[chat_id] = True
            await context.bot.send_message(chat_id, "Enter points per round (e.g., 24):", reply_markup=ForceReply())
            return

        await show_standings(chat_id, context)
        await next_pair(chat_id, context)

    elif data in ["score_team1", "score_team2"]:
        pair = pending_scores[chat_id]['pair']
        selected_team = pair.team1 if data == "score_team1" else pair.team2
        pending_scores[chat_id]['selected_team'] = selected_team

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

        await context.bot.send_message(
            chat_id,
            f"Selected team:\n{' & '.join(p.name for p in selected_team)}\nEnter score:",
            reply_markup=ForceReply()
        )

    elif data == "finish_tournament":
        await finalize_tournament(chat_id, context)

# -------------------- Messages --------------------

async def handle_message(update, context):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if update.message.reply_to_message and "Enter tournament name" in update.message.reply_to_message.text:
        if chat_id in pending_tournament_name:
            selected = pending_tournament_name[chat_id]
            t = Tournament(text)
            for name in selected:
                t.add_player(Player(name))
            tournaments[t.id] = t
            chat_tournaments[chat_id] = {'t_id': t.id}
            
            del pending_tournament_name[chat_id]
            
            await update.message.reply_text(f"Tournament '{text}' created!")
            await show_tournament_mode(chat_id, context)
            
            pending_round_points[chat_id] = True
            await context.bot.send_message(chat_id, "Enter points per round (e.g., 24):", reply_markup=ForceReply())
        return

    if chat_id in pending_new_player and pending_new_player[chat_id]:
        if text and text not in players_pool:
            players_pool.append(text)
        del pending_new_player[chat_id]
        await show_player_selection(update, context, chat_id)
        return

    if chat_id in pending_round_points:
        try:
            value = int(text)
            t = tournaments[chat_tournaments[chat_id]['t_id']]
            if t.round_points is not None:
                del pending_round_points[chat_id]
                return
            t.round_points = value

            await update.message.reply_text(f"Points per round set to {value}")
            await show_standings(chat_id, context)
            await next_pair(chat_id, context)

            del pending_round_points[chat_id]
        except:
            await update.message.reply_text("Enter a valid number (e.g., 24)")
        return

    if chat_id in pending_scores and 'selected_team' in pending_scores[chat_id]:
        try:
            score = int(text)
            t = tournaments[chat_tournaments[chat_id]['t_id']]
            pair = pending_scores[chat_id]['pair']
            selected_team = pending_scores[chat_id]['selected_team']
            other_team = [p for p in pair.team1 + pair.team2 if p not in selected_team]

            opponent_score = t.round_points - score

            # Обновление статистики
            for p in pair.team1 + pair.team2:
                p.games_played += 1

            if score == opponent_score:
                for p in pair.team1 + pair.team2:
                    p.draws += 1
                    p.points += score
            elif score > opponent_score:
                for p in selected_team:
                    p.wins += 1
                    p.points += score
                for p in other_team:
                    p.losses += 1
                    p.points += opponent_score
            else:
                for p in selected_team:
                    p.losses += 1
                    p.points += score
                for p in other_team:
                    p.wins += 1
                    p.points += opponent_score

            # Set score in team1 - team2 order
            if selected_team == pair.team1:
                team1_score = score
                team2_score = opponent_score
            else:
                team1_score = opponent_score
                team2_score = score
            pair.score = f"{team1_score}-{team2_score}"

            # Добавляем в историю
            t.round_history.append({
                "round": t.round,
                "team1": [p.name for p in pair.team1],
                "team2": [p.name for p in pair.team2],
                "score": pair.score
            })

            await context.bot.send_message(chat_id, f"🏁 Round finished\nScore: {pair.score}")

            del pending_scores[chat_id]
            t.round += 1
            await show_standings(chat_id, context)
            await next_pair(chat_id, context)

        except:
            await update.message.reply_text("Enter a valid number")

# -------------------- Standings --------------------

async def show_standings(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        lines.append(f"{i}. {p.name:<{max_name_len}} | Games: {p.games_played:<2} | W: {p.wins:<2} | D: {p.draws:<2} | L: {p.losses:<2} | Pts: {p.points:<3}")
    msg = "📊 Standings:\n<pre>\n" + "\n".join(lines) + "\n</pre>"

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML")
        except:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML")
            t.stats_msg_id = sent.message_id
    else:
        sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML")
        t.stats_msg_id = sent.message_id

# -------------------- Finalization & Export --------------------

async def finalize_tournament(chat_id, context):
    t = tournaments[chat_tournaments[chat_id]['t_id']]
    t.players.sort(key=lambda p: (-p.points, -p.wins))

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

    # Delete standings message
    if t.stats_msg_id:
        try:
            await context.bot.delete_message(chat_id, t.stats_msg_id)
        except:
            pass

    # Show final standings without buttons
    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        lines.append(f"{i}. {p.name:<{max_name_len}} | Games: {p.games_played:<2} | W: {p.wins:<2} | D: {p.draws:<2} | L: {p.losses:<2} | Pts: {p.points:<3}")
    msg = "🏆 Tournament Finished!\n📊 Final Standings:\n<pre>\n" + "\n".join(lines) + "\n</pre>"
    await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    # --- Export CSV ---
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
        await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred. Please try again.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
