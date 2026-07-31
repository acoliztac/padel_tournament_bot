import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter

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
            await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg,
                                         parse_mode="HTML",
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
            await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg,
                                         parse_mode="HTML",
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
        await safe_edit_message_text(bot=context.bot, chat_id=chat_id,
                                     message_id=chat_tournaments[chat_id]['players_msg_id'], text=msg_text,
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
        success = await safe_edit_message_text(bot=context.bot, chat_id=chat_id,
                                               message_id=chat_tournaments[chat_id]['tournament_msg_id'], text=msg_text,
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


async def delete_score_message(chat_id, context):
    if chat_id in pending_scores and pending_scores[chat_id].get('score_msg_id'):
        await safe_delete_message(context.bot, chat_id, pending_scores[chat_id]['score_msg_id'])
