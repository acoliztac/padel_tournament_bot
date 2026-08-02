import pytest

from bot.tournament import Player, Tournament
from bot.utils import score_helpers
from bot.services import round_service
from bot import state


@pytest.fixture
def tournament_with_result():
    t = Tournament(name="RoundTest")
    # Set round points to even number so half is integer
    t.round_points = 8

    players = [Player(name=f"p{i}") for i in range(1, 5)]
    for p in players:
        t.add_player(p)

    team1 = [players[0], players[1]]
    team2 = [players[2], players[3]]

    # Apply an initial match result: team1 wins 6-2
    score_helpers.apply_match_result(team1, team2, 6, 2)

    # Add round history entry
    t.round_history.append({
        "round": 1,
        "team1": [p.name for p in team1],
        "team2": [p.name for p in team2],
        "score": "6-2",
    })

    return t


def test_set_round_draw_service_rolls_back_and_updates_history(tournament_with_result):
    chat_id = 12345
    t = tournament_with_result

    # register tournament in global state
    state.tournaments[t.id] = t
    state.chat_tournaments[chat_id] = {"t_id": t.id}

    # Pre-check: winners have wins and points
    team1_players = t.players[0:2]
    team2_players = t.players[2:4]
    assert all(p.wins == 1 for p in team1_players)
    assert all(p.losses == 1 for p in team2_players)

    # Change result to draw
    success = round_service.set_round_draw_service(chat_id=chat_id, round_num=1)
    assert success is True

    # Round history updated
    half = t.round_points // 2
    assert t.round_history[0]["score"] == f"{half}-{half}"

    # Old wins/losses were rolled back and new draws applied
    for p in t.players:
        assert p.wins == 0
        assert p.losses == 0
        assert p.draws == 1
        assert p.points == half

    # games_played should remain from original match (apply_match_result incremented them)
    assert all(p.games_played == 1 for p in t.players)
