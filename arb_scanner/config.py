"""Configuration constants for markets, bookmakers, and sports."""

from __future__ import annotations

BASE_URL = "https://api.the-odds-api.com/v4/sports"

# Australian bookmakers exposed by The Odds API (key → display name)
TARGET_BOOKS: dict[str, str] = {
    "betfair_ex_au": "Betfair Exchange",
    "betr_au": "Betr",
    "ladbrokes_au": "Ladbrokes",
    "neds": "Neds",
    "pointsbetau": "PointsBet",
    "sportsbet": "Sportsbet",
    "tab": "TAB",
    "unibet": "Unibet",
}

# Common sports with AU bookmaker coverage
SPORTS: dict[str, str] = {
    "aussierules_afl": "AFL",
    "rugbyleague_nrl": "NRL",
    "soccer_epl": "EPL",
    "basketball_nba": "NBA",
    "tennis_atp_aus_open": "Tennis - Aus Open",
    "soccer_australia_aleague": "A-League",
    "cricket_big_bash": "Big Bash",
    "cricket_test_match": "Cricket Tests",
    "mma_mixed_martial_arts": "MMA/UFC",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "americanfootball_nfl": "NFL",
    "soccer_uefa_champs_league": "UCL",
}

DEFAULT_SPORTS = ("aussierules_afl", "rugbyleague_nrl")
DEFAULT_STAKE = 1000.0
