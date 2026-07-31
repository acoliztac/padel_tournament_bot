from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.tournament import Tournament

def calculate_fair_table(tournament: Tournament) -> list:
    """
    FAIR TABLE: Normalize all players to the minimum number of games.
    VALUE = P - O/2 (player's score - opponent's score/2)
    Remove the least valuable matches until all have equal games.
    Now also includes wins, losses, and draws count.
    """
    if not tournament.round_history:
        return []

    # Create player data structure with all matches
    player_matches = {}
    for p in tournament.players:
        player_matches[p.name] = []

    # Collect all matches for each player
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score1, score2 = map(int, round_data["score"].split("-"))

        # Add match to both team members
        for player_name in team1:
            player_matches[player_name].append({
                "round": round_data["round"],
                "teammate": team1[0] if team1[0] != player_name else team1[1],
                "opponents": team2,
                "player_score": score1,
                "opponent_score": score2,
                "value": score1 - score2 / 2
            })

        for player_name in team2:
            player_matches[player_name].append({
                "round": round_data["round"],
                "teammate": team2[0] if team2[0] != player_name else team2[1],
                "opponents": team1,
                "player_score": score2,
                "opponent_score": score1,
                "value": score2 - score1 / 2
            })

    # Find minimum games played
    min_games = min(len(matches) for matches in player_matches.values()) if player_matches else 0

    # Calculate normalized stats
    normalized_stats = []
    for player_name, matches in player_matches.items():
        # Sort by value ascending (remove least valuable first)
        sorted_matches = sorted(matches, key=lambda m: m["value"])

        # Keep only min_games matches
        kept_matches = sorted_matches[len(sorted_matches) - min_games:] if len(
            sorted_matches) > min_games else sorted_matches

        total_points = sum(m["player_score"] for m in kept_matches)
        games = len(kept_matches)

        # Count wins, losses, and draws
        wins = 0
        losses = 0
        draws = 0
        for match in kept_matches:
            if match["player_score"] > match["opponent_score"]:
                wins += 1
            elif match["player_score"] < match["opponent_score"]:
                losses += 1
            else:
                draws += 1

        normalized_stats.append({
            "player": player_name,
            "games": games,
            "points": total_points,
            "wins": wins,
            "losses": losses,
            "draws": draws
        })

    # Sort by points (descending), then by wins (descending), then player name
    normalized_stats.sort(key=lambda x: (-x["points"], -x["wins"], x["player"]))

    return normalized_stats


def calculate_fun_table(tournament: Tournament) -> list:
    """
    FUN TABLE: Measure "interestingness" of matches.
    fun per match = max(0, 10 - abs(score_diff))
    Divided by number of games played to get average fun score per game.
    """
    if not tournament.round_history:
        return []

    player_fun = {}
    player_games = {}
    for p in tournament.players:
        player_fun[p.name] = 0
        player_games[p.name] = 0

    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score1, score2 = map(int, round_data["score"].split("-"))

        score_diff = abs(score1 - score2)
        fun_score = max(0, 10 - score_diff)

        # Add fun score to all players in the match
        for player_name in team1 + team2:
            player_fun[player_name] += fun_score
            player_games[player_name] += 1

    # Create result list with average fun score per game
    fun_stats = []
    for name in player_fun.keys():
        avg_fun = player_fun[name] / player_games[name] if player_games[name] > 0 else 0
        fun_stats.append({
            "player": name,
            "fun_score": round(avg_fun, 2),
            "total_fun": player_fun[name],
            "games": player_games[name]
        })

    # Sort by average fun_score descending, then by player name for deterministic ordering
    fun_stats.sort(key=lambda x: (-x["fun_score"], x["player"]))

    return fun_stats


def calculate_tense_matches(tournament: Tournament) -> list:
    """
    TENSE MATCHES: Find the most intense matches based on close score differences.
    Tension score = 10 - abs(score_diff) (same as fun_score)
    Returns top 5 matches sorted by tension.
    """
    if not tournament.round_history:
        return []

    tense_matches = []
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score = round_data["score"]
        score1, score2 = map(int, score.split("-"))

        score_diff = abs(score1 - score2)
        tension_score = max(0, 10 - score_diff)

        tense_matches.append({
            "round": round_data["round"],
            "team1": f"{team1[0]} & {team1[1]}",
            "team2": f"{team2[0]} & {team2[1]}",
            "score": score,
            "tension": tension_score,
            "score_diff": score_diff
        })

    # Sort by tension descending, then by score_diff ascending
    tense_matches.sort(key=lambda x: (-x["tension"], x["score_diff"]))

    # Return top 5
    return tense_matches[:3]


def calculate_best_worst_partners(tournament):
    if not tournament.round_history:
        return {}

    # -------------------------
    # data structures
    # -------------------------
    partners = defaultdict(lambda: defaultdict(list))
    enemies = defaultdict(lambda: defaultdict(list))

    # -------------------------
    # PROCESS MATCHES
    # -------------------------
    for r in tournament.round_history:
        team1 = r["team1"]
        team2 = r["team2"]
        s1, s2 = map(int, r["score"].split("-"))

        diff = s1 - s2  # team1 perspective
        opp_diff = s2 - s1  # team2 perspective

        # -------------------------
        # TEAM 1
        # -------------------------
        for p in team1:
            partner = team1[0] if team1[1] == p else team1[1]

            # 🤝 partner effect
            partners[p][partner].append(diff)

            # 😈 enemies effect
            for e in team2:
                enemies[p][e].append(diff)

        # -------------------------
        # TEAM 2
        # -------------------------
        for p in team2:
            partner = team2[0] if team2[1] == p else team2[1]

            # 🤝 partner effect
            partners[p][partner].append(opp_diff)

            # 😈 enemies effect
            for e in team1:
                enemies[p][e].append(opp_diff)

    # -------------------------
    # FINAL CALCULATION
    # -------------------------
    result = {}

    for player in partners.keys():

        # 🤝 best partner
        best_partner = None
        best_avg = None
        partners_summary = {}

        for pr, vals in partners[player].items():
            avg = sum(vals) / len(vals)

            partners_summary[pr] = {
                "avg": round(avg, 2),
                "games": len(vals)
            }

            if best_avg is None or avg > best_avg:
                best_avg = avg
                best_partner = pr

        # 😈 worst enemy
        worst_enemy = None
        worst_avg = None
        enemies_summary = {}

        for en, vals in enemies[player].items():
            avg = sum(vals) / len(vals)

            enemies_summary[en] = {
                "avg": round(avg, 2),
                "games": len(vals)
            }

            if worst_avg is None or avg < worst_avg:
                worst_avg = avg
                worst_enemy = en

        result[player] = {
            "favorite_partner": best_partner,
            "favorite_avg": round(best_avg, 2) if best_avg is not None else None,
            "worst_enemy": worst_enemy,
            "worst_enemy_avg": round(worst_avg, 2) if worst_avg is not None else None,
            "partners": partners_summary,
            "opponents": enemies_summary
        }

    return result


def get_raw_match_table(tournament):
    """
    RAW MATCH TABLE: Display all matches in order.
    """
    if not tournament.round_history:
        return []

    matches = []
    for round_data in tournament.round_history:
        team1 = round_data["team1"]
        team2 = round_data["team2"]
        score = round_data["score"]

        matches.append({
            "round": round_data["round"],
            "team1": f"{team1[0]} & {team1[1]}",
            "score": score,
            "team2": f"{team2[0]} & {team2[1]}"
        })

    return matches
