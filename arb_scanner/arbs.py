"""Arbitrage detection and stake allocation."""

from __future__ import annotations

from typing import Any

from arb_scanner.config import DEFAULT_STAKE, TARGET_BOOKS


def allocate_stakes(odds: dict[str, float], total_stake: float) -> dict[str, float]:
    """Allocate stakes so each outcome pays the same return."""
    implied_sum = sum(1.0 / price for price in odds.values())
    return {
        outcome: round(total_stake * (1.0 / price) / implied_sum, 2)
        for outcome, price in odds.items()
    }


def implied_probability_sum(odds: dict[str, float]) -> float:
    """Sum of inverse decimal odds; < 1.0 implies a theoretical arbitrage."""
    return sum(1.0 / price for price in odds.values())


def profit_percent(implied_sum: float) -> float:
    """Convert an implied-probability sum into profit percentage on total stake."""
    return (1.0 / implied_sum - 1.0) * 100


def _book_display_name(book_key: str) -> str | None:
    """Return configured display name, or None if the book is not a target."""
    return TARGET_BOOKS.get(book_key)


def find_h2h_arbs(
    events: list[dict[str, Any]],
    threshold: float = 0.0,
    total_stake: float = DEFAULT_STAKE,
) -> list[dict[str, Any]]:
    """
    Find head-to-head (moneyline) arbitrage opportunities.

    For 2-way markets (e.g. tennis): 1/odds_A + 1/odds_B < 1
    For 3-way markets (e.g. soccer with draw): sum of three inverses < 1
    """
    arbs: list[dict[str, Any]] = []

    for event in events:
        bookmakers = event.get("bookmakers", [])
        if len(bookmakers) < 2:
            continue

        book_odds: dict[str, dict[str, float]] = {}
        for bm in bookmakers:
            bm_name = _book_display_name(bm.get("key", ""))
            if bm_name is None:
                continue
            for market in bm.get("markets", []):
                if market.get("key") == "h2h":
                    outcomes = {o["name"]: float(o["price"]) for o in market.get("outcomes", [])}
                    if outcomes:
                        book_odds[bm_name] = outcomes

        if len(book_odds) < 2:
            continue

        all_outcomes = sorted({name for outcomes in book_odds.values() for name in outcomes})

        best_odds: dict[str, float] = {}
        best_books: dict[str, str] = {}
        for outcome in all_outcomes:
            best_price = 0.0
            best_book: str | None = None
            for book_name, outcomes in book_odds.items():
                price = outcomes.get(outcome, 0.0)
                if price > best_price:
                    best_price = price
                    best_book = book_name
            if best_price > 0 and best_book is not None:
                best_odds[outcome] = best_price
                best_books[outcome] = best_book

        if len(best_odds) != len(all_outcomes) or not best_odds:
            continue

        implied_sum = implied_probability_sum(best_odds)
        if implied_sum >= 1.0:
            continue

        pct = profit_percent(implied_sum)
        if pct < threshold:
            continue

        stakes = allocate_stakes(best_odds, total_stake)
        guaranteed_return = round(total_stake / implied_sum, 2)

        arbs.append(
            {
                "event": f"{event.get('home_team', '?')} vs {event.get('away_team', '?')}",
                "sport": event.get("sport_title", ""),
                "commence": event.get("commence_time", ""),
                "profit_pct": round(pct, 3),
                "implied_sum": round(implied_sum, 5),
                "bets": [
                    {
                        "outcome": outcome,
                        "book": best_books[outcome],
                        "odds": best_odds[outcome],
                        "stake": stakes[outcome],
                    }
                    for outcome in all_outcomes
                ],
                "total_stake": total_stake,
                "guaranteed_return": guaranteed_return,
                "guaranteed_profit": round(guaranteed_return - total_stake, 2),
                "all_book_odds": book_odds,
            }
        )

    return sorted(arbs, key=lambda item: -item["profit_pct"])


def find_spread_total_arbs(
    events: list[dict[str, Any]],
    market_type: str = "spreads",
    threshold: float = 0.0,
    total_stake: float = DEFAULT_STAKE,
) -> list[dict[str, Any]]:
    """
    Find arbitrage on spreads or totals markets.

    Opposing sides on the same line can form an arb when
    1/best_over + 1/best_under < 1 (or equivalent for spread sides).
    """
    arbs: list[dict[str, Any]] = []

    for event in events:
        bookmakers = event.get("bookmakers", [])
        if len(bookmakers) < 2:
            continue

        lines_by_point: dict[Any, dict[str, list[dict[str, Any]]]] = {}
        for bm in bookmakers:
            bm_name = _book_display_name(bm.get("key", ""))
            if bm_name is None:
                continue
            for market in bm.get("markets", []):
                if market.get("key") != market_type:
                    continue
                for outcome in market.get("outcomes", []):
                    point = outcome.get("point", 0)
                    name = outcome["name"]
                    price = float(outcome["price"])
                    lines_by_point.setdefault(point, {}).setdefault(name, []).append(
                        {"book": bm_name, "price": price}
                    )

        for point, sides in lines_by_point.items():
            side_names = list(sides.keys())
            if len(side_names) != 2:
                continue

            side_a, side_b = side_names
            best_a = max(sides[side_a], key=lambda item: item["price"])
            best_b = max(sides[side_b], key=lambda item: item["price"])

            odds = {side_a: best_a["price"], side_b: best_b["price"]}
            implied_sum = implied_probability_sum(odds)
            if implied_sum >= 1.0:
                continue

            pct = profit_percent(implied_sum)
            if pct < threshold:
                continue

            stakes = allocate_stakes(odds, total_stake)
            guaranteed_return = round(total_stake / implied_sum, 2)

            arbs.append(
                {
                    "event": f"{event.get('home_team', '?')} vs {event.get('away_team', '?')}",
                    "sport": event.get("sport_title", ""),
                    "market": f"{market_type} @ {point}",
                    "profit_pct": round(pct, 3),
                    "implied_sum": round(implied_sum, 5),
                    "bets": [
                        {
                            "outcome": side_a,
                            "book": best_a["book"],
                            "odds": best_a["price"],
                            "stake": stakes[side_a],
                            "line": point,
                        },
                        {
                            "outcome": side_b,
                            "book": best_b["book"],
                            "odds": best_b["price"],
                            "stake": stakes[side_b],
                            "line": point,
                        },
                    ],
                    "total_stake": total_stake,
                    "guaranteed_return": guaranteed_return,
                    "guaranteed_profit": round(guaranteed_return - total_stake, 2),
                }
            )

    return sorted(arbs, key=lambda item: -item["profit_pct"])
