def rollback_match_result(team1, team2, score1, score2):
    """
    Rollback player statistics after removing/changing match result.
    Does not change games_played.
    """

    if score1 == score2:
        for p in team1 + team2:
            p.draws -= 1
            p.points -= score1

    elif score1 > score2:
        for p in team1:
            p.wins -= 1
            p.points -= score1

        for p in team2:
            p.losses -= 1
            p.points -= score2

    else:
        for p in team1:
            p.losses -= 1
            p.points -= score1

        for p in team2:
            p.wins -= 1
            p.points -= score2


def rollback_match(team1, team2, score1, score2):
    """
    Rollback complete match statistics including games played.
    Used when match is removed from active statistics.
    """

    for p in team1 + team2:
        p.games_played -= 1

    rollback_match_result(team1, team2, score1, score2)


def apply_win(winner_team, loser_team, winner_score, loser_score):
    """
    Apply winning result to players.
    """

    for p in winner_team:
        p.wins += 1
        p.points += winner_score

    for p in loser_team:
        p.losses += 1
        p.points += loser_score


def apply_draw(team1, team2, points):
    """
    Apply draw result to players.
    """

    for p in team1 + team2:
        p.draws += 1
        p.points += points


def apply_match_result(team1, team2, score1, score2):
    """
    Apply full match result.
    """

    for p in team1 + team2:
        p.games_played += 1

    if score1 == score2:
        apply_draw(
            team1,
            team2,
            score1
        )

    elif score1 > score2:
        apply_win(
            team1,
            team2,
            score1,
            score2
        )

    else:
        apply_win(
            team2,
            team1,
            score2,
            score1
        )
