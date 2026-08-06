"""Unit tests for arbitrage detection math (no live API calls)."""

from __future__ import annotations

from arb_scanner.arbs import (
    allocate_stakes,
    find_h2h_arbs,
    find_spread_total_arbs,
    implied_probability_sum,
    profit_percent,
)


def test_implied_sum_and_profit():
    odds = {"A": 2.10, "B": 2.10}
    implied = implied_probability_sum(odds)
    assert implied < 1.0
    assert abs(profit_percent(implied) - ((1 / implied) - 1) * 100) < 1e-9


def test_allocate_stakes_equalises_returns():
    odds = {"Home": 2.20, "Away": 2.00}
    stakes = allocate_stakes(odds, total_stake=1000)
    returns = {k: stakes[k] * odds[k] for k in odds}
    assert abs(returns["Home"] - returns["Away"]) < 0.05
    assert abs(sum(stakes.values()) - 1000) < 0.02


def _event(home, away, books_h2h):
    """
    books_h2h: list of (api_key, {outcome: price})
    """
    return {
        "home_team": home,
        "away_team": away,
        "sport_title": "Test Sport",
        "commence_time": "2030-01-01T00:00:00Z",
        "bookmakers": [
            {
                "key": key,
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [{"name": n, "price": p} for n, p in outcomes.items()],
                    }
                ],
            }
            for key, outcomes in books_h2h
        ],
    }


def test_find_h2h_arb_two_way():
    events = [
        _event(
            "Team A",
            "Team B",
            [
                ("sportsbet", {"Team A": 2.20, "Team B": 1.80}),
                ("ladbrokes_au", {"Team A": 1.90, "Team B": 2.15}),
            ],
        )
    ]
    # Best: Team A @ 2.20 (Sportsbet), Team B @ 2.15 (Ladbrokes)
    # 1/2.20 + 1/2.15 ≈ 0.920 < 1 → arb
    arbs = find_h2h_arbs(events, threshold=0.0, total_stake=1000)
    assert len(arbs) == 1
    arb = arbs[0]
    assert arb["event"] == "Team A vs Team B"
    assert arb["profit_pct"] > 0
    books = {bet["outcome"]: bet["book"] for bet in arb["bets"]}
    assert books["Team A"] == "Sportsbet"
    assert books["Team B"] == "Ladbrokes"


def test_find_h2h_no_arb_when_overround():
    events = [
        _event(
            "Team A",
            "Team B",
            [
                ("sportsbet", {"Team A": 1.90, "Team B": 1.90}),
                ("ladbrokes_au", {"Team A": 1.91, "Team B": 1.91}),
            ],
        )
    ]
    # Best still 1.91 + 1.91 → implied > 1
    assert find_h2h_arbs(events) == []


def test_ignores_non_target_bookmakers():
    events = [
        _event(
            "Team A",
            "Team B",
            [
                ("sportsbet", {"Team A": 1.50, "Team B": 2.50}),
                # Fictional key not in TARGET_BOOKS — must not be used
                ("fantasy_book", {"Team A": 5.00, "Team B": 5.00}),
            ],
        )
    ]
    # Only one target book → no cross-book arb
    assert find_h2h_arbs(events) == []


def test_threshold_filters_small_edges():
    events = [
        _event(
            "Team A",
            "Team B",
            [
                ("sportsbet", {"Team A": 2.05, "Team B": 1.95}),
                ("ladbrokes_au", {"Team A": 1.95, "Team B": 2.05}),
            ],
        )
    ]
    small = find_h2h_arbs(events, threshold=0.0)
    assert len(small) == 1
    assert find_h2h_arbs(events, threshold=50.0) == []


def test_find_totals_arb():
    events = [
        {
            "home_team": "Team A",
            "away_team": "Team B",
            "sport_title": "NBA",
            "bookmakers": [
                {
                    "key": "sportsbet",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 2.10, "point": 220.5},
                                {"name": "Under", "price": 1.80, "point": 220.5},
                            ],
                        }
                    ],
                },
                {
                    "key": "tab",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.85, "point": 220.5},
                                {"name": "Under", "price": 2.10, "point": 220.5},
                            ],
                        }
                    ],
                },
            ],
        }
    ]
    arbs = find_spread_total_arbs(events, market_type="totals", total_stake=1000)
    assert len(arbs) == 1
    assert "totals @ 220.5" in arbs[0]["market"]
    assert arbs[0]["profit_pct"] > 0
