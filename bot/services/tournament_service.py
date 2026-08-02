from datetime import datetime

from bot.state import chat_tournaments, pending_scores, tournaments
from bot.tournament import Player, Tournament
from bot.utils.state_helpers import clear_active_round_state, clear_management_state
from bot.utils.tournaments_helpers import get_tournament


def create_tournament_service(chat_id, selected):
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


def select_next_pair_service(chat_id):
    tournament = get_tournament(chat_id=chat_id)

    pair = tournament.select_next_pair()

    if pair:
        pending_scores[chat_id] = {"pair": pair}

    return pair


def finalize_tournament_service(chat_id):
    t = get_tournament(chat_id=chat_id)

    t.players.sort(key=lambda p: (-p.points, -p.wins))

    tournaments.pop(t.id, None)

    clear_management_state(chat_id)
    clear_active_round_state(chat_id)

    return t


def set_round_points_service(chat_id, points):
    t = get_tournament(chat_id=chat_id)
    t.round_points = points
