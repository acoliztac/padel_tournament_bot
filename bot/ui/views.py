import asyncio

from telegram.error import RetryAfter, TelegramError

from bot.state import (
    anti_spam_msg_ids,
    chat_tournaments,
    pending_edit_selection,
    pending_management,
    pending_manual_pair,
    pending_player_selection,
    pending_scores,
    players_pool,
)
from bot.ui.keyboards import (
    begin_tournament_setup_keyboard,
    edit_rounds_keyboard,
    management_keyboard,
    manual_pair_keyboard,
    player_selection_keyboard,
    points_selection_keyboard,
    round_result_keyboard,
    score_keyboard,
    tournament_mode_keyboard,
)
from bot.utils.telegram_helpers import safe_delete_message, safe_edit_message_text
from bot.utils.tournament_reports import (
    add_best_worst_partners_table,
    add_fair_table,
    add_final_table,
    add_fun_table,
    add_raw_match_table,
    add_tense_matches_table,
)
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
            f"{i}. {p.name:<{max_name_len}} | "
            f"Игры: {p.games_played:<2} | "
            f"П: {p.wins:<2} | "
            f"Н: {p.draws:<2} | "
            f"Пр: {p.losses:<2} | "
            f"Оч: {p.points:<3}")
    msg = (
            f"🏆 {t.name}\n"
            f"⚡ Очки за раунд: {t.round_points}\n\n"
            f"📊 Турнирная таблица:\n<pre>\n"
            + "\n".join(lines)
            + "\n</pre>"
    )

    # Add round history
    if t.round_history:
        msg += "\n\n📜 История раундов:"
        for i, r in enumerate(t.round_history):
            team1_str = f"{r['team1'][0]} & {r['team1'][1]}"
            team2_str = f"{r['team2'][0]} & {r['team2'][1]}"

            score1, score2 = map(int, r['score'].split('-'))

            if score1 == score2:
                result = "Ничья"
            elif score1 > score2:
                result = "Победа команды 🔹"
            else:
                result = "Победа команды 🔸"
            msg += (
                f"\n\n🏓 Раунд {r['round']}\n"
                f"🔹 {team1_str}\n\tvs\n"
                f"🔸 {team2_str}\n"
                f"Счёт: {r['score']}, {result}\n"
                "<code>────────────────────────</code>")
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
            msg_prefix = f"🏓 Раунд {t.current_round}"

        equal_games = t.will_round_equalize_games(pair.team1 + pair.team2)

        msg += (f"\n\n{msg_prefix}\n"
                f"🔹 {pair.team1[0].name} & {pair.team1[1].name}\n"
                f"\tvs\n"
                f"🔸 {pair.team2[0].name} & {pair.team2[1].name}\n\n"
                f"Выберите победителя {"⚖️" if equal_games else ""}:")

        keyboard = round_result_keyboard()

    if chat_id in pending_edit_selection:
        keyboard = edit_rounds_keyboard(t.round_history)

        edited = await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg,
                                              parse_mode="HTML", reply_markup=keyboard)
        if not edited:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=keyboard)
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if chat_id in pending_management:
        keyboard = management_keyboard(bool(t.round_history))
        edited = await safe_edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                              reply_markup=keyboard)
        if not edited:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=keyboard)
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

        keyboard = manual_pair_keyboard(players=t.players, team1=team1, team2=team2)
        edited = await safe_edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                              reply_markup=keyboard)
        if not edited:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=keyboard)
            t.stats_msg_id = sent.message_id
        return  # Не показывать обычные standings

    if t.stats_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=t.stats_msg_id, text=msg, parse_mode="HTML",
                                                reply_markup=keyboard if keyboard else None)
        except RetryAfter as e:

            try:
                sent = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
                anti_spam_msg_ids[chat_id] = sent.message_id
            except TelegramError:
                pass
            await asyncio.sleep(e.retry_after)
            await safe_edit_message_text(bot=context.bot, chat_id=chat_id, message_id=t.stats_msg_id, text=msg,
                                         parse_mode="HTML", reply_markup=keyboard if keyboard else None)
        except TelegramError:
            await safe_delete_message(context.bot, chat_id, t.stats_msg_id)
            try:
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                      reply_markup=keyboard if keyboard else None)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                      reply_markup=keyboard if keyboard else None)
            t.stats_msg_id = sent.message_id
    else:
        try:
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=keyboard if keyboard else None)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            sent = await context.bot.send_message(chat_id, msg, parse_mode="HTML",
                                                  reply_markup=keyboard if keyboard else None)
        t.stats_msg_id = sent.message_id


async def show_player_selection(query, context, chat_id):
    selected = pending_player_selection[chat_id]['selected']

    keyboard = await player_selection_keyboard(selected, players_pool)

    msg_text = "В турнире принимают участие:\n" + "\n".join(
        f"- {p}" for p in selected) if selected else "Игроки не выбраны"

    if chat_tournaments.get(chat_id, {}).get('players_msg_id'):
        await safe_edit_message_text(bot=context.bot, chat_id=chat_id,
                                     message_id=chat_tournaments[chat_id]['players_msg_id'], text=msg_text,
                                     reply_markup=keyboard)
    elif query.message:
        sent_msg = await query.message.reply_text(msg_text, reply_markup=keyboard)
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id
    else:
        sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=keyboard)
        if chat_id not in chat_tournaments:
            chat_tournaments[chat_id] = {}
        chat_tournaments[chat_id]['players_msg_id'] = sent_msg.message_id


async def show_score_buttons(chat_id, context, winner_team):
    t = get_tournament(chat_id=chat_id)

    keyboard = score_keyboard(t.round_points)
    msg_text = f"Выигравшая команда:\n{' & '.join(p.name for p in winner_team)}\nВыберите счёт:"
    try:
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=keyboard)
        pending_scores[chat_id]['score_msg_id'] = sent.message_id
    except RetryAfter as e:
        try:
            sent_anti = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
            anti_spam_msg_ids[chat_id] = sent_anti.message_id
        except TelegramError:
            pass
        await asyncio.sleep(e.retry_after)
        sent = await context.bot.send_message(chat_id, msg_text, reply_markup=keyboard)
        pending_scores[chat_id]['score_msg_id'] = sent.message_id


async def show_tournament_mode(chat_id, context):
    keyboard = tournament_mode_keyboard()
    msg_text = "Турнир в процессе..."

    if chat_tournaments[chat_id].get('tournament_msg_id'):
        success = await safe_edit_message_text(bot=context.bot, chat_id=chat_id,
                                               message_id=chat_tournaments[chat_id]['tournament_msg_id'], text=msg_text,
                                               reply_markup=keyboard)
        if not success:
            sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=keyboard)
            chat_tournaments[chat_id]['tournament_msg_id'] = sent_msg.message_id
    else:
        sent_msg = await context.bot.send_message(chat_id, msg_text, reply_markup=keyboard)
        chat_tournaments[chat_id]['tournament_msg_id'] = sent_msg.message_id


async def show_points_selection(chat_id, context):
    keyboard = points_selection_keyboard()
    sent = await context.bot.send_message(chat_id, "Выберите количество очков за раунд:", reply_markup=keyboard)
    chat_tournaments[chat_id]['points_msg_id'] = sent.message_id


async def delete_score_message(chat_id, context):
    if chat_id in pending_scores and pending_scores[chat_id].get('score_msg_id'):
        await safe_delete_message(context.bot, chat_id, pending_scores[chat_id]['score_msg_id'])


async def show_final_report(chat_id, context, text, message_id=None):
    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML")
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await safe_edit_message_text(context.bot, chat_id, message_id, text, parse_mode="HTML")
        except TelegramError:
            pass  # If edit fails, just proceed
    else:
        try:
            await context.bot.send_message(chat_id, text, parse_mode="HTML")
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await context.bot.send_message(chat_id, text, parse_mode="HTML")


async def show_new_tournament_button(chat_id, context):
    keyboard = begin_tournament_setup_keyboard()

    try:
        await context.bot.send_message(chat_id, "Начать новый турнир?", reply_markup=keyboard)
    except RetryAfter as e:
        try:
            sent_anti = await context.bot.send_message(chat_id, f"Антиспам сработал, ждем {e.retry_after} секунд...")
            anti_spam_msg_ids[chat_id] = sent_anti.message_id
        except TelegramError:
            pass

        await asyncio.sleep(e.retry_after)
        await context.bot.send_message(chat_id, "Начать новый турнир?", reply_markup=keyboard)


def build_final_report(t):
    # Show final standings without buttons
    max_name_len = max(len(p.name) for p in t.players)

    msg = ""

    msg = add_final_table(max_name_len, msg, t)
    msg = add_raw_match_table(msg, t)
    msg = add_fair_table(max_name_len, msg, t)
    msg = add_tense_matches_table(msg, t)
    msg = add_fun_table(max_name_len, msg, t)
    msg = add_best_worst_partners_table(max_name_len, msg, t)

    return msg
