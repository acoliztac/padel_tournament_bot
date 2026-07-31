from bot.analytics import calculate_best_worst_partners, calculate_tense_matches, calculate_fun_table, \
    calculate_fair_table, get_raw_match_table


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
