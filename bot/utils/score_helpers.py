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