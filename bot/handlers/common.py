import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter

from bot.analytics import get_raw_match_table, calculate_fair_table, calculate_fun_table, calculate_best_worst_partners, \
    calculate_tense_matches
from bot.state import chat_tournaments, anti_spam_msg_ids, pending_scores, pending_manual_pair, pending_edit_selection, \
    players_pool, pending_player_selection, pending_management
from bot.utils.telegram_helpers import safe_edit_message_reply_markup, safe_delete_message, safe_edit_message_text

from bot.utils.tournaments_helpers import get_tournament


async def show_standings(chat_id, context):
    if chat_id in anti_spam_msg_ids:
        await safe_delete_message(context.bot, chat_id, anti_spam_msg_ids[chat_id])
        del anti_spam_msg_ids[chat_id]

    t = get_tournament(chat_id=chat_id)
    t.players.sort(key=lambda p: (-p.points, -p.wins))

    max_name_len = max(len(p.name) for p in t.players)
    lines = []
    for i, p in enumerate(t.players, 1):
        lines.append(
            f"{i}. {p.name:<{max_name_len}} | Игры: {p.games_played:<2} | П: {p.wins:<2} | Н: {p.draws:<2} | Пр: {p.losses:<2} | Оч: {p.points:<3}")
    msg = f"🏆 {t.name}\n⚡ Очки за раунд: {t.round_points}\n\n📊 Турнирная таблица:\n<pre>\n" + "\n".join(
        lines) + "\n</pre>"

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
            round_num = pending_scores[chat_id].get('edit_round', t.current_round - 1)
            msg_prefix = f"Редактировать раунд {round_num}"
        else:
            round_num = t.current_round
            msg_prefix = f"🏓 Раунд {round_num}"
        equal_games = t.will_round_equalize_games(pair.team1 + pair.team2)
        equal_icon = "⚖️" if equal_games else ""
        msg += f"\n\n{msg_prefix}\n🔹 {pair.team1[0].name} & {pair.team1[1].name}\n\tvs\n🔸 {pair.team2[0].name} & {pair.team2[1].name}\n\nВыберите победителя {equal_icon}:"
        keyboard = [[
            InlineKeyboardButton("Ничья", callback_data="set_draw"),
            InlineKeyboardButton("Win: 🔹 ", callback_data="result_team1"),
            InlineKeyboardButton("Win: 🔸 ", callback_data="result_team2")
        ]]

    if not (chat_id in pending_edit_selection or chat_id in pending_manual_pair):
        keyboard.append([InlineKeyboardButton("⚙️ Управление", callback_data="management")])

    if chat_id in pending_edit_selection:
        keyboard = []
        for r in t.round_history:
            keyboard.append(
                [InlineKeyboardButton(f"Редактировать раунд {r['round']}", callback_data=f"edit_round_{r['round']}")])
            keyboard.append([InlineKeyboardButton(f"Ничья", callback_data=f"set_draw_round_{r['round']}"),
                             InlineKeyboardButton(f"Win: 🔹 ", callback_data=f"set_winner_team1_round_{r['round']}"),
                             InlineKeyboardButton(f"Win: 🔸 ", callback_data=f"set_winner_team2_round_{r['round']}")])
        keyboard.append([InlineKeyboardButton("Вернуться к таблице", callback_data="back_to_standings")])
        try:
            await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(keyboard))
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if chat_id in pending_management:
        keyboard = []
        keyboard.append([
            InlineKeyboardButton("🔄 Перегенерировать команды", callback_data="regenerate_auto"),
            InlineKeyboardButton("👉 Ручная генерация команд", callback_data="regenerate_manual")
        ])
        if t.round_history:
            keyboard.append([InlineKeyboardButton("Редактировать раунды", callback_data="edit_rounds")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_standings")])
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(keyboard))
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if chat_id in pending_manual_pair:
        team1 = pending_manual_pair[chat_id]['team1']
        team2 = pending_manual_pair[chat_id]['team2']
        round_num = t.current_round
        msg = f"Ручная генерация команд для Раунда {round_num}:\n"
        msg += f"Команда 1: {', '.join(team1) if team1 else 'Пусто'}\n"
        msg += f"Команда 2: {', '.join(team2) if team2 else 'Пусто'}\n\n"
        msg += "Выберите игроков:"
        keyboard = []
        available_players = [p.name for p in t.players if p.name not in team1 and p.name not in team2]
        for player in available_players:
            keyboard.append([
                InlineKeyboardButton(f"➕ 1: {player}", callback_data=f"add_to_team1_{player}"),
                InlineKeyboardButton(f"➕ 2: {player}", callback_data=f"add_to_team2_{player}")
            ])
        # Кнопки для удаления
        for player in team1 + team2:
            team = "1" if player in team1 else "2"
            keyboard.append([InlineKeyboardButton(f"➖ Удалить {player} из Команды {team}",
                                                  callback_data=f"remove_from_team_{player}")])
        # Кнопки действий
        keyboard.append([
            InlineKeyboardButton("✅ Подтвердить команды", callback_data="confirm_manual_pair"),
            InlineKeyboardButton("🔄 Сбросить", callback_data="reset_manual_pair"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_pair")
        ])
        # Отправить или редактировать сообщение
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(keyboard))
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except RetryAfter as e:
            try:
                sent = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
                anti_spam_msg_ids[chat_id] = sent.message_id
            except:
                pass
            await asyncio.sleep(e.retry_after)
            await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except:
            await safe_delete_message(context.bot, chat_id, t.stats_msg_id)
            try:
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                      reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                      reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
            t.stats_msg_id = sent.message_id
    else:
        try:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        t.stats_msg_id = sent.message_id


async def show_score_buttons(chat_id, context, winner_team):
    t = get_tournament(chat_id=chat_id)
    half = t.round_points // 2
    buttons = [InlineKeyboardButton(str(i), callback_data=f"set_score_{i}") for i in
               range(half + 1, t.round_points + 1)]
    keyboard = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]  # 4 buttons per row
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


async def show_player_selection(query, context, chat_id):
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

    msg_text = "В турнире принимают участие:\n" + "\n".join(
        f"- {p}" for p in selected) if selected else "Игроки не выбраны"

    if chat_tournaments.get(chat_id, {}).get('players_msg_id'):
        await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=chat_tournaments[chat_id]['players_msg_id'], text=msg_text,
                                     reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.message:
        sent_msg = await query.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id
    else:
        sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id


async def show_tournament_mode(chat_id, context):
    t = get_tournament(chat_id=chat_id)
    keyboard = [[InlineKeyboardButton("Завершить турнир", callback_data="finish_tournament")]]
    msg_text = "Турнир в процессе..."

    if chat_tournaments[chat_id].get('tournament_msg_id'):
        success = await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=chat_tournaments[chat_id]['tournament_msg_id'], text=msg_text,
                                         reply_markup=InlineKeyboardMarkup(keyboard))
        if not success:
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
    sent = await context.bot.send_message(chat_id, "Выберите количество очков за раунд:",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
    chat_tournaments[chat_id]['points_msg_id'] = sent.message_id


async def add_final_table(max_name_len: int, msg: str, t) -> str:
    lines = []
    for i, p in enumerate(t.players, 1):
        medal = "▫️"
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        lines.append(
            f"{medal} {i}. {p.name:<{max_name_len}} | Игры: {p.games_played:<2} | П: {p.wins:<2} | Н: {p.draws:<2} | Пр: {p.losses:<2} | Оч: {p.points:<3}")
    msg += f"\n\n🏆 {t.name}\n📊 Полные результаты (без корректировки игр):\n<pre>\n" + "\n".join(lines) + "\n</pre>"
    return msg


async def add_raw_match_table(msg: str, t) -> str:
    raw_matches = get_raw_match_table(t)
    matches_lines = []
    if raw_matches:
        max_team_len = max(len(m['team1']) for m in raw_matches)
        for match in raw_matches:
            matches_lines.append(
                f"R{match['round']:3} | {match['team1']:<{max_team_len}} | {match['score']:<5} | {match['team2']}")
        msg += "\n\n📜 История раундов:\n<pre>\n" + "\n".join(matches_lines) + "\n</pre>"
    return msg


async def add_fun_table(max_name_len: int, msg: str, t) -> str:
    fun_table = calculate_fun_table(t)
    fun_lines = []
    for i, entry in enumerate(fun_table, 1):
        fun_lines.append(
            f"{i}. {entry['player']:<{max_name_len}} | Средн. зрелищность: {entry['fun_score']:<5} | Игры: {entry['games']:<2}")
    msg += "\n\n⚔️ Игроки с самыми зрелищными матчами:\n<pre>\n" + "\n".join(fun_lines) + "\n</pre>"
    return msg


async def add_fair_table(max_name_len: int, msg: str, t) -> str:
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
        fair_lines.append(
            f"{medal} {i}. {entry['player']:<{max_name_len}} | Игры: {entry['games']:<2} | П: {entry['wins']:<2} | Н: {entry['draws']:<2} | Пр: {entry['losses']:<2} | Оч: {entry['points']:<3}")
    msg += "\n\n⚖️ Нормализованные результаты:\n<pre>\n" + "\n".join(fair_lines) + "\n</pre>"
    return msg


async def add_tense_matches_table(msg: str, t) -> str:
    """Add the most tense matches to the message"""
    tense_matches = calculate_tense_matches(t)
    if not tense_matches:
        return msg

    tense_lines = []
    for i, match in enumerate(tense_matches, 1):
        tension_emoji = "🔥" if match["tension"] > 0 else "❄️"
        tense_lines.append(
            f"{i}. R{match['round']} | {match['team1']} vs {match['team2']} | Счёт: {match['score']} {tension_emoji}")

    msg += "\n\n🔥 Самые зрелищные матчи (Топ 3):\n<pre>\n" + "\n".join(tense_lines) + "\n</pre>"
    return msg


async def add_best_worst_partners_table(max_name_len: int, msg: str, t) -> str:
    """Add best and worst partners for each player to the message"""
    partners = calculate_best_worst_partners(t)
    if not partners:
        return msg

    partners_lines = []
    for player_name in sorted(partners.keys()):
        info = partners[player_name]
        best_partner = info["favorite_partner"]
        best_avg = info["favorite_avg"]
        worst_partner = info["worst_enemy"]
        worst_avg = info["worst_enemy_avg"]

        if best_partner and worst_partner:
            partners_lines.append(
                f"{player_name:<{max_name_len}}: ❤️ {best_partner:<{max_name_len}} ({best_avg:+.1f}) | 😈 {worst_partner:<{max_name_len}} ({worst_avg:+.1f})")

    if partners_lines:
        msg += "\n\n🤝 Любимые партнёры и злейшие враги:\n<pre>\n" + "\n".join(partners_lines) + "\n</pre>"
    return msg


async def remove_buttons_from_standings_message(chat_id, context, t):
    if t.stats_msg_id:
        await safe_edit_message_reply_markup(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id,
                                             reply_markup=None)


async def delete_points_selection_message(chat_id, context):
    if chat_tournaments[chat_id].get('points_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['points_msg_id'])


async def delete_round_message(chat_id, context):
    if chat_tournaments[chat_id].get('round_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['round_msg_id'])


async def delete_tournament_mode_message(chat_id, context):
    if chat_tournaments[chat_id].get('tournament_msg_id'):
        await safe_delete_message(context.bot, chat_id, chat_tournaments[chat_id]['tournament_msg_id'])


async def delete_score_message(chat_id, context):
    if chat_id in pending_scores and pending_scores[chat_id].get('score_msg_id'):
        await safe_delete_message(context.bot, chat_id, pending_scores[chat_id]['score_msg_id'])
