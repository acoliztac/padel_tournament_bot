import pytest

from bot.tournament import Player
from bot.utils import score_helpers


@pytest.fixture
def four_players():
    return [Player(name=f"p{i}") for i in range(1, 5)]


def test_apply_win_updates_wins_and_points(four_players):
    team1 = four_players[:2]
    team2 = four_players[2:]

    score_helpers.apply_win(winner_team=team1, loser_team=team2, winner_score=6, loser_score=3)

    for p in team1:
        assert p.wins == 1
        assert p.points == 6

    for p in team2:
        assert p.losses == 1
        assert p.points == 3


def test_apply_draw_updates_draws_and_points(four_players):
    team1 = four_players[:2]
    team2 = four_players[2:]

    score_helpers.apply_draw(team1=team1, team2=team2, points=4)

    for p in team1 + team2:
        assert p.draws == 1
        assert p.points == 4


def test_rollback_match_result_and_rollback_match(four_players):
    team1 = four_players[:2]
    team2 = four_players[2:]

    # Apply a win then rollback result
    score_helpers.apply_win(team1, team2, winner_score=6, loser_score=3)
    # simulate games played increment from a full match
    for p in team1 + team2:
        p.games_played += 1

    # Now rollback full match
    score_helpers.rollback_match(team1, team2, 6, 3)

    # games_played rolled back
    for p in team1 + team2:
        assert p.games_played == 0

    # wins/losses rolled back and points removed
    for p in team1 + team2:
        assert p.wins == 0 and p.losses == 0
        assert p.points == 0

    # Test rollback of draw specifically
    score_helpers.apply_draw(team1, team2, points=4)
    # draw recorded
    for p in team1 + team2:
        assert p.draws == 1
        assert p.points == 4

    score_helpers.rollback_match_result(team1, team2, 4, 4)
    for p in team1 + team2:
        assert p.draws == 0
        assert p.points == 0
