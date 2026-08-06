"""Terminal formatting for odds comparisons and arb reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tabulate import tabulate

from arb_scanner.config import TARGET_BOOKS


def display_arbs(arbs: list[dict[str, Any]], title: str = "Arbitrage Opportunities") -> None:
    """Pretty-print arbitrage opportunities."""
    if not arbs:
        print(f"\n  No {title.lower()} found.\n")
        return

    print(f"\n{'=' * 70}")
    print(f"  {title} - {len(arbs)} found")
    print(f"{'=' * 70}")

    for index, arb in enumerate(arbs, 1):
        print(f"\n  [{index}] {arb['event']}")
        print(f"      Sport: {arb['sport']}")
        if "market" in arb:
            print(f"      Market: {arb['market']}")
        print(
            f"      Profit: {arb['profit_pct']:.3f}%  "
            f"(implied sum: {arb['implied_sum']:.5f})"
        )
        print()

        bet_table = [
            [
                bet["outcome"],
                bet["book"],
                f"{bet['odds']:.2f}",
                f"${bet['stake']:.2f}",
            ]
            for bet in arb["bets"]
        ]

        table = tabulate(
            bet_table,
            headers=["Outcome", "Bookmaker", "Odds", "Stake"],
            tablefmt="simple",
            stralign="left",
        )
        print("      " + table.replace("\n", "\n      "))

        print(f"\n      Total stake: ${arb['total_stake']:.2f}")
        print(f"      Guaranteed return: ${arb['guaranteed_return']:.2f}")
        print(f"      Guaranteed profit: ${arb['guaranteed_profit']:.2f}")
        print(f"  {'-' * 60}")

    print()


def display_odds_comparison(events: list[dict[str, Any]], max_events: int = 10) -> None:
    """Show a side-by-side odds comparison for the first N events."""
    print(f"\n{'=' * 70}")
    print(f"  Odds Comparison (showing up to {max_events} events)")
    print(f"{'=' * 70}\n")

    for event in events[:max_events]:
        print(f"  {event.get('home_team', '?')} vs {event.get('away_team', '?')}")
        commence = event.get("commence_time", "")
        if commence:
            try:
                dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                print(f"  Starts: {dt.strftime('%a %d %b %Y %H:%M %Z')}")
            except ValueError:
                print(f"  Starts: {commence}")

        rows: list[list[str]] = []
        for bm in event.get("bookmakers", []):
            bm_name = TARGET_BOOKS.get(bm.get("key", ""), bm.get("key", ""))
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                odds_str = "  |  ".join(
                    f"{o['name']}: {float(o['price']):.2f}" for o in market.get("outcomes", [])
                )
                rows.append([bm_name, odds_str])

        if rows:
            print(tabulate(rows, headers=["Book", "Odds"], tablefmt="simple", stralign="left"))
        else:
            print("  No odds available from target books.")
        print()
