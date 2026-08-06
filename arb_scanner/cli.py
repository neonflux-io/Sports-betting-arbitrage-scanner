"""CLI entrypoint for the arbitrage scanner."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from tabulate import tabulate

from arb_scanner import __version__
from arb_scanner.arbs import find_h2h_arbs, find_spread_total_arbs
from arb_scanner.client import OddsAPIClient, OddsAPIError
from arb_scanner.config import DEFAULT_SPORTS, DEFAULT_STAKE, SPORTS, TARGET_BOOKS
from arb_scanner.display import display_arbs, display_odds_comparison


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arb-scanner",
        description=(
            "Scan Australian bookmakers for sports-betting arbitrage opportunities "
            "using The Odds API."
        ),
    )
    parser.add_argument(
        "--key",
        default=None,
        help="Odds API key (or set ODDS_API_KEY in the environment / .env)",
    )
    parser.add_argument(
        "--sport",
        default=None,
        help=f"Sport key to scan. Options: {', '.join(SPORTS.keys())}",
    )
    parser.add_argument(
        "--all-sports",
        action="store_true",
        help="Scan all configured sports (consumes more API quota)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum profit %% to report (default: 0.0)",
    )
    parser.add_argument(
        "--stake",
        type=float,
        default=DEFAULT_STAKE,
        help=f"Total stake used for allocation display (default: {DEFAULT_STAKE:g})",
    )
    parser.add_argument(
        "--show-odds",
        action="store_true",
        help="Show full head-to-head odds comparison tables",
    )
    parser.add_argument(
        "--list-sports",
        action="store_true",
        help="List sports available from The Odds API",
    )
    parser.add_argument(
        "--list-books",
        action="store_true",
        help="List configured Australian bookmakers",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def resolve_api_key(cli_key: str | None) -> str:
    key = cli_key or os.getenv("ODDS_API_KEY")
    if not key:
        print(
            "Error: provide an API key with --key or set ODDS_API_KEY "
            "(see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def scan_sport(
    client: OddsAPIClient,
    sport_key: str,
    sport_name: str,
    threshold: float,
    stake: float,
    show_odds: bool,
) -> list[dict]:
    """Scan one sport across h2h, spreads, and totals markets."""
    print(f"\n{'-' * 70}")
    print(f"  Scanning: {sport_name} ({sport_key})")
    print(f"{'-' * 70}")

    h2h_arbs: list[dict] = []

    try:
        events = client.get_odds(sport_key, markets="h2h")
        quota = client.last_quota
        print(
            f"  API quota: {quota.get('used', '?')} used / "
            f"{quota.get('remaining', '?')} remaining this month"
        )
        print(f"  Found {len(events)} events with h2h odds")

        if show_odds and events:
            display_odds_comparison(events)

        h2h_arbs = find_h2h_arbs(events, threshold=threshold, total_stake=stake)
        display_arbs(h2h_arbs, f"H2H Arbs - {sport_name}")
    except OddsAPIError as exc:
        print(f"  {exc}")
        return []

    for market_type, title in (("spreads", "Spread"), ("totals", "Totals")):
        try:
            market_events = client.get_odds(sport_key, markets=market_type)
            market_arbs = find_spread_total_arbs(
                market_events,
                market_type=market_type,
                threshold=threshold,
                total_stake=stake,
            )
            display_arbs(market_arbs, f"{title} Arbs - {sport_name}")
        except OddsAPIError:
            # Market simply may not be offered for this sport right now.
            pass

    return h2h_arbs


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    print("\n" + "=" * 70)
    print("  AU SPORTS ARBITRAGE SCANNER")
    print(f"  Target books: {', '.join(TARGET_BOOKS.values())}")
    print(f"  Threshold: {args.threshold}% profit  |  Stake model: ${args.stake:.2f}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if args.list_books:
        print("\nConfigured Australian bookmakers:")
        for key, name in TARGET_BOOKS.items():
            print(f"  {key:20s} -> {name}")
        print("\nEdit TARGET_BOOKS in arb_scanner/config.py to customise.")
        return

    api_key = resolve_api_key(args.key)
    client = OddsAPIClient(api_key)

    if args.list_sports:
        print("\nFetching available sports...")
        try:
            sports = client.get_sports()
        except OddsAPIError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        rows = [
            [s.get("key", ""), s.get("title", ""), s.get("group", ""), "yes" if s.get("active") else ""]
            for s in sports
        ]
        print(tabulate(rows, headers=["Key", "Title", "Group", "Active"], tablefmt="simple"))
        return

    if args.all_sports:
        sport_keys = list(SPORTS.keys())
    elif args.sport:
        sport_keys = [args.sport]
    else:
        sport_keys = list(DEFAULT_SPORTS)

    all_arbs: list[dict] = []
    for sport_key in sport_keys:
        sport_name = SPORTS.get(sport_key, sport_key)
        arbs = scan_sport(
            client,
            sport_key,
            sport_name,
            threshold=args.threshold,
            stake=args.stake,
            show_odds=args.show_odds,
        )
        all_arbs.extend(arbs)

    print("\n" + "=" * 70)
    print(f"  SCAN COMPLETE - {len(all_arbs)} H2H arb opportunities found")
    if all_arbs:
        best = max(all_arbs, key=lambda item: item["profit_pct"])
        print(f"  Best: {best['event']} @ {best['profit_pct']:.3f}% profit")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
