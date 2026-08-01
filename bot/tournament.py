from dataclasses import dataclass, field
from typing import Optional
import uuid
import random


@dataclass
class Player:
    name: str
    games_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    current_pair: Optional["Pair"] = field(
        default=None,
        repr=False,
        compare=False
    )


@dataclass
class Pair:
    team1: list[Player]
    team2: list[Player]
    score: Optional[str] = None


@dataclass
class Tournament:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    players: list[Player] = field(default_factory=list)
    current_round: int = 1
    round_history: list = field(default_factory=list)
    stats_msg_id: Optional[int] = None
    round_points: Optional[int] = None

    def add_player(self, player: Player):
        self.players.append(player)

    def create_pair(self, team1: list[Player], team2: list[Player]) -> Pair:
        pair = Pair(team1=team1, team2=team2)

        for player in team1 + team2:
            player.current_pair = pair

        return pair

    def create_manual_pair(self, team1_names: list[str], team2_names: list[str]) -> Optional[Pair]:
        if len(team1_names) != 2 or len(team2_names) != 2:
            return None

        selected_names = team1_names + team2_names
        if len(set(selected_names)) != 4:
            return None

        players_by_name = {player.name: player for player in self.players}

        try:
            team1 = [players_by_name[name] for name in team1_names]
            team2 = [players_by_name[name] for name in team2_names]
        except KeyError:
            return None

        pair = self.create_pair(team1, team2)
        return pair

    def will_round_equalize_games(
            self,
            selected_players: list[Player]
    ) -> bool:
        # Check if all players will have the same games_played after the current round
        after_games = [p.games_played + (1 if p in selected_players else 0) for p in self.players]
        return len(set(after_games)) == 1

    # -------------------- Mexicano 1+4 vs 2+3 --------------------
    def select_next_pair(self) -> Optional[Pair]:
        if len(self.players) < 4:
            return None

        # 4 players with the least number of games
        available_players = sorted(
            self.players,
            key=lambda p: (
                p.games_played,
                random.random()
            )
        )

        selected = available_players[:4]

        # Sort by points: p1=max, p2>=p3, p4=min
        sorted_players = sorted(
            selected,
            key=lambda p: p.points,
            reverse=True
        )

        p1, p2, p3, p4 = sorted_players

        team1 = [p1, p4]
        team2 = [p2, p3]

        return self.create_pair(team1, team2)
