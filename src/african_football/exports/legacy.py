"""
legacy.py — Make the legacy match format from SourceMatch records.

The JSON and TXT files of the pipeline use a format that the old
Soccerway scraper made. This module makes the same format from
SourceMatch records. Thus, the files do not change when the pipeline
uses the new source adapters.

The legacy format has these special rules:
    - For a penalty shootout, home_score and away_score contain the
      shootout score. full_time_score contains the score before the
      shootout, for example '0-0'.
    - All scores are text, for example '3', not 3.
    - The halftime score has spaces, for example '2 - 1'.
    - The date has the format 'DD.MM.YYYY'. If the kick-off time is
      known, the format is 'DD.MM.YYYY HH:MM'.
    - An awarded match always has the awarded_reason 'walkover'.

Do not use this format for new outputs. It is only for the current
JSON and TXT files.
"""

from typing import Any, Optional

from african_football.models.source_match import MatchStatus, SourceMatch


def _legacy_date(match: SourceMatch) -> str:
    """Return 'DD.MM.YYYY', 'DD.MM.YYYY HH:MM', or '' if there is no date."""
    if match.match_date is None:
        return ""
    text = match.match_date.strftime("%d.%m.%Y")
    if match.kickoff_local is not None:
        text += match.kickoff_local.strftime(" %H:%M")
    return text


def _text(value: Optional[int]) -> Optional[str]:
    return str(value) if value is not None else None


def to_legacy_match(match: SourceMatch) -> dict[str, Any]:
    """
    Make one legacy match dictionary from a SourceMatch.

    The keys have the same sequence as in the old scraper. Thus, the
    JSON files have the same text.

    Args:
        match: The SourceMatch record.

    Returns:
        The match dictionary in the legacy format.
    """
    awarded = match.status is MatchStatus.AWARDED

    halftime = None
    if match.ht_home is not None and match.ht_away is not None:
        halftime = f"{match.ht_home} - {match.ht_away}"

    if match.pen_home is not None and match.pen_away is not None:
        shootout = True
        home_score, away_score = str(match.pen_home), str(match.pen_away)
        full_time = f"{match.home_goals}-{match.away_goals}"
        winner = "home" if match.pen_home > match.pen_away else "away"
    else:
        shootout = False
        home_score, away_score = _text(match.home_goals), _text(match.away_goals)
        full_time = None
        winner = None

    return {
        "stage": match.stage,
        "round": match.round_name,
        "round_number": match.round_number,
        "date": _legacy_date(match),
        "home_team": match.home_team_raw,
        "away_team": match.away_team_raw,
        "home_score": home_score,
        "away_score": away_score,
        "half_time_score": halftime,
        "match_url": match.source_url,
        "awarded": awarded,
        "awarded_reason": "walkover" if awarded else None,
        "full_time_score": full_time,
        "penalty_shootout": shootout,
        "penalty_winner": winner,
    }


def to_legacy_stages(matches: list[SourceMatch]) -> list[dict[str, Any]]:
    """
    Put legacy match dictionaries into stages, in the sequence of the matches.

    The old scraper gave a list of stages. Each stage has its name, the
    highest round number, the number of matches, and the matches.

    Args:
        matches: The SourceMatch records of one season, in page sequence.

    Returns:
        A list of stage dictionaries: stage_name, total_rounds,
        total_matches and matches.
    """
    stages: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        stages.setdefault(match.stage or "", []).append(to_legacy_match(match))

    result = []
    for name, stage_matches in stages.items():
        rounds = [
            m["round_number"] for m in stage_matches if m["round_number"] is not None
        ]
        result.append(
            {
                "stage_name": name,
                "total_rounds": max(rounds) if rounds else 0,
                "total_matches": len(stage_matches),
                "matches": stage_matches,
            }
        )
    return result
