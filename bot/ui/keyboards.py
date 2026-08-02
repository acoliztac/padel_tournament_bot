# bot/ui/keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def player_selection_keyboard(selected, players) -> InlineKeyboardMarkup:
    keyboard = []
    for i, name in enumerate(players):
        if name not in selected:
            keyboard.append([InlineKeyboardButton(f"✓ {name}", callback_data=f"select_player_{i}")])
        else:
            keyboard.append([InlineKeyboardButton(f"✗ {name}", callback_data=f"deselect_player_{i}")])

    keyboard.append([InlineKeyboardButton("Добавить нового игрока", callback_data="add_new_player")])

    if len(selected) < len(players):
        keyboard.append([InlineKeyboardButton("Выбрать всех", callback_data="select_all_players")])

    if len(selected) > 0:
        keyboard.append([InlineKeyboardButton("Удалить выбранных", callback_data="delete_player")])

    if len(selected) >= 4:
        keyboard.append([InlineKeyboardButton("Начать турнир", callback_data="create_tournament")])
    return InlineKeyboardMarkup(keyboard)


def management_keyboard(has_history=False):
    keyboard = [[
        InlineKeyboardButton("🔄 Перегенерировать команды", callback_data="regenerate_auto"),
        InlineKeyboardButton("👉 Ручная генерация команд", callback_data="regenerate_manual")
    ]]

    if has_history:
        keyboard.append([
            InlineKeyboardButton("Редактировать раунды", callback_data="edit_rounds")
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_standings")
    ])

    return InlineKeyboardMarkup(keyboard)


def tournament_mode_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Завершить турнир", callback_data="finish_tournament")
        ]
    ])


def points_selection_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("16", callback_data="set_round_points_16"),
            InlineKeyboardButton("24", callback_data="set_round_points_24"),
            InlineKeyboardButton("32", callback_data="set_round_points_32"),
        ]
    ])


def round_result_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Ничья", callback_data="set_draw"),
            InlineKeyboardButton("Win: 🔹", callback_data="result_team1"),
            InlineKeyboardButton("Win: 🔸", callback_data="result_team2"),
        ],
        [
            InlineKeyboardButton("⚙️ Управление", callback_data="management")
        ]
    ])


def begin_tournament_setup_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Начать новый турнир", callback_data="begin_tournament_setup")
        ]
    ])


def score_keyboard(round_points):
    half = round_points // 2

    buttons = [
        InlineKeyboardButton(str(i), callback_data=f"set_score_{i}")
        for i in range(half + 1, round_points + 1)
    ]

    rows = [
        buttons[i:i + 4]
        for i in range(0, len(buttons), 4)
    ]

    return InlineKeyboardMarkup(rows)


def edit_rounds_keyboard(round_history):
    keyboard = []

    for r in round_history:
        keyboard.append([
            InlineKeyboardButton(f"Редактировать раунд {r['round']}", callback_data=f"edit_round_{r['round']}")
        ])

        keyboard.append([
            InlineKeyboardButton("Ничья", callback_data=f"set_draw_round_{r['round']}"),
            InlineKeyboardButton("Win: 🔹", callback_data=f"set_winner_team1_round_{r['round']}"),
            InlineKeyboardButton("Win: 🔸", callback_data=f"set_winner_team2_round_{r['round']}")
        ])

    keyboard.append([
        InlineKeyboardButton("Вернуться к таблице", callback_data="back_to_standings")
    ])

    return InlineKeyboardMarkup(keyboard)


def manual_pair_keyboard(players, team1, team2):
    keyboard = []

    available_players = [p.name for p in players if p.name not in team1 and p.name not in team2]

    for player in available_players:
        keyboard.append([
            InlineKeyboardButton(f"➕ 1: {player}", callback_data=f"add_to_team1_{player}"),
            InlineKeyboardButton(f"➕ 2: {player}", callback_data=f"add_to_team2_{player}")
        ])

    for player in team1 + team2:
        team = "1" if player in team1 else "2"

        keyboard.append([
            InlineKeyboardButton(f"➖ Удалить {player} из Команды {team}", callback_data=f"remove_from_team_{player}")
        ])

    keyboard.append([
        InlineKeyboardButton("✅ Подтвердить команды", callback_data="confirm_manual_pair"),
        InlineKeyboardButton("🔄 Сбросить", callback_data="reset_manual_pair"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_pair")
    ])

    return InlineKeyboardMarkup(keyboard)
