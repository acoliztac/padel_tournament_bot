import pytest

from bot.tournament import Player, Tournament


@pytest.fixture
def players():
    return [Player(name=f"p{i}") for i in range(1, 7)]


@pytest.fixture
def tournament():
    t = Tournament(name="T")
    for i in range(1, 7):
        p = Player(name=f"p{i}")
        t.add_player(p)
    return t


def test_player_creation():
    p = Player(name="Alice")
    assert p.name == "Alice"
    assert p.games_played == 0
    assert p.wins == 0 and p.losses == 0 and p.draws == 0 and p.points == 0


def test_add_player():
    t = Tournament(name="Test")
    p = Player(name="New")
    t.add_player(p)
    assert p in t.players


def test_create_manual_pair_valid(tournament):
    names = [p.name for p in tournament.players[:4]]
    pair = tournament.create_manual_pair(team1_names=names[:2], team2_names=names[2:4])
    assert pair is not None
    assert len(pair.team1) == 2 and len(pair.team2) == 2


def test_create_manual_pair_duplicates(tournament):
    names = [tournament.players[0].name, tournament.players[0].name]
    pair = tournament.create_manual_pair(team1_names=names, team2_names=["p3", "p4"])
    assert pair is None


def test_create_manual_pair_wrong_size(tournament):
    pair = tournament.create_manual_pair(team1_names=["p1"], team2_names=["p2", "p3"])
    assert pair is None


def test_select_next_pair_respects_games_and_forms_teams():
    # Create tournament with 6 players with distinct games_played and points to be deterministic
    t = Tournament(name="Sel")
    players = []
    for i, (gp, pts) in enumerate([(0, 10), (1, 8), (2, 6), (3, 4), (4, 2), (5, 0)], start=1):
        p = Player(name=f"p{i}")
        p.games_played = gp
        p.points = pts
        players.append(p)
        t.add_player(p)

    pair = t.select_next_pair()
    assert pair is not None

    # Selected should be four players with smallest games_played (p1..p4)
    selected_names = {p.name for p in pair.team1 + pair.team2}
    assert selected_names == {"p1", "p2", "p3", "p4"}

    # Teams should be formed as [p1, p4] and [p2, p3] because sorted by points desc
    team1_names = [p.name for p in pair.team1]
    team2_names = [p.name for p in pair.team2]
    assert set(team1_names) == {"p1", "p4"}
    assert set(team2_names) == {"p2", "p3"}
