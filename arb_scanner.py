import argparse
import requests
import json
from datetime import datetime
from itertools import product as iter_product
from tabulate import tabulate

# ─── Config ───────────────────────────────────────────────────────────────────

BASE_URL = "https://api.the-odds-api.com/v4/sports"

# All Australian bookmakers available on The Odds API
TARGET_BOOKS = {
    "betfair_ex_au": "Betfair Exchange",
    "betr_au":       "Betr",
    "ladbrokes_au":  "Ladbrokes",
    "neds":          "Neds",
    "pointsbetau":   "PointsBet",
    "sportsbet":     "Sportsbet",
    "tab":           "TAB",
    "unibet":        "Unibet",
}

# Popular sports available for Australia on The Odds API
SPORTS = {
    "aussierules_afl":       "AFL",
    "rugbyleague_nrl":       "NRL",
    "soccer_epl":            "EPL",
    "basketball_nba":        "NBA",
    "tennis_atp_aus_open":   "Tennis - Aus Open",
    "soccer_australia_aleague": "A-League",
    "cricket_big_bash":      "Big Bash",
    "cricket_test_match":    "Cricket Tests",
    "mma_mixed_martial_arts": "MMA/UFC",
    "baseball_mlb":          "MLB",
    "icehockey_nhl":         "NHL",
    "americanfootball_nfl":  "NFL",
    "soccer_uefa_champs_league": "UCL",
}


# ─── Core Functions ───────────────────────────────────────────────────────────

def get_available_sports(api_key: str) -> list:
    """Fetch all currently available sports from the API."""
    resp = requests.get(f"{BASE_URL}", params={"apiKey": api_key})
    resp.raise_for_status()
    return resp.json()


def get_odds(api_key: str, sport: str, markets: str = "h2h") -> list:
    """
    Fetch odds for a sport. Each request costs 1 towards your monthly quota.
    
    Markets: 'h2h' (moneyline), 'spreads', 'totals'
    """
    params = {
        "apiKey": api_key,
        "regions": "au",          # All Australian bookmakers
        "markets": markets,
        "oddsFormat": "decimal",
    }
    resp = requests.get(f"{BASE_URL}/{sport}/odds", params=params)
    resp.raise_for_status()
    
    # Print remaining quota from headers
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    print(f"  API quota: {used} used / {remaining} remaining this month")
    
    return resp.json()


def find_h2h_arbs(events: list, threshold: float = 0.0) -> list:
    """
    Find arbitrage opportunities on head-to-head (moneyline) markets.
    
    For a 2-outcome event (e.g. tennis), arb exists when:
        1/odds_A + 1/odds_B < 1
    
    For a 3-outcome event (e.g. soccer with draw), arb exists when:
        1/odds_A + 1/odds_draw + 1/odds_B < 1
    
    Args:
        events: List of event dicts from the API
        threshold: Minimum profit % to report (0.0 = report all arbs)
    
    Returns:
        List of arb opportunities with details
    """
    arbs = []
    
    for event in events:
        bookmakers = event.get("bookmakers", [])
        if len(bookmakers) < 2:
            continue
        
        # Get h2h market from each bookmaker
        book_odds = {}
        for bm in bookmakers:
            bm_key = bm["key"]
            bm_name = TARGET_BOOKS.get(bm_key, bm_key)
            for market in bm.get("markets", []):
                if market["key"] == "h2h":
                    outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
                    book_odds[bm_name] = outcomes
        
        if len(book_odds) < 2:
            continue
        
        # Get all outcome names
        all_outcomes = set()
        for outcomes in book_odds.values():
            all_outcomes.update(outcomes.keys())
        all_outcomes = sorted(all_outcomes)
        
        # For each outcome, find the best (highest) odds across books
        best_odds = {}
        best_books = {}
        for outcome in all_outcomes:
            best_price = 0
            best_book = None
            for book_name, outcomes in book_odds.items():
                price = outcomes.get(outcome, 0)
                if price > best_price:
                    best_price = price
                    best_book = book_name
            if best_price > 0:
                best_odds[outcome] = best_price
                best_books[outcome] = best_book
        
        # Check if all outcomes are covered
        if len(best_odds) != len(all_outcomes):
            continue
        
        # Calculate implied probability sum
        implied_sum = sum(1.0 / odds for odds in best_odds.values())
        
        # Arb exists if implied_sum < 1
        if implied_sum < 1.0:
            profit_pct = (1.0 / implied_sum - 1.0) * 100
            
            if profit_pct >= threshold:
                # Calculate optimal stake allocation for $1000 total
                total_stake = 1000
                stakes = {}
                for outcome in all_outcomes:
                    stake = total_stake * (1.0 / best_odds[outcome]) / implied_sum
                    stakes[outcome] = round(stake, 2)
                
                guaranteed_return = round(total_stake / implied_sum, 2)
                guaranteed_profit = round(guaranteed_return - total_stake, 2)
                
                arbs.append({
                    "event": f"{event.get('home_team', '?')} vs {event.get('away_team', '?')}",
                    "sport": event.get("sport_title", ""),
                    "commence": event.get("commence_time", ""),
                    "profit_pct": round(profit_pct, 3),
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
                    "guaranteed_profit": guaranteed_profit,
                    "all_book_odds": book_odds,
                })
    
    return sorted(arbs, key=lambda x: -x["profit_pct"])


def find_spread_total_arbs(events: list, market_type: str = "spreads", threshold: float = 0.0) -> list:
    """
    Find arbs on spreads or totals markets.
    
    For spreads/totals, arb exists when two books offer opposite sides
    at a combined implied probability < 100%.
    
    e.g. Book A: Over 220.5 @ 2.10, Book B: Under 220.5 @ 2.05
         Implied: 1/2.10 + 1/2.05 = 0.476 + 0.488 = 0.964 < 1 → arb!
    """
    arbs = []
    
    for event in events:
        bookmakers = event.get("bookmakers", [])
        if len(bookmakers) < 2:
            continue
        
        # Collect all lines by point value
        lines_by_point = {}
        for bm in bookmakers:
            bm_name = TARGET_BOOKS.get(bm["key"], bm["key"])
            for market in bm.get("markets", []):
                if market["key"] == market_type:
                    for outcome in market["outcomes"]:
                        point = outcome.get("point", 0)
                        name = outcome["name"]
                        price = outcome["price"]
                        
                        if point not in lines_by_point:
                            lines_by_point[point] = {}
                        if name not in lines_by_point[point]:
                            lines_by_point[point][name] = []
                        lines_by_point[point][name].append({
                            "book": bm_name,
                            "price": price,
                        })
        
        # For each point line, check for arbs across opposite sides
        for point, sides in lines_by_point.items():
            side_names = list(sides.keys())
            if len(side_names) != 2:
                continue
            
            side_a, side_b = side_names
            
            # Find best odds for each side
            best_a = max(sides[side_a], key=lambda x: x["price"])
            best_b = max(sides[side_b], key=lambda x: x["price"])
            
            implied_sum = 1.0 / best_a["price"] + 1.0 / best_b["price"]
            
            if implied_sum < 1.0:
                profit_pct = (1.0 / implied_sum - 1.0) * 100
                if profit_pct >= threshold:
                    total_stake = 1000
                    stake_a = round(total_stake * (1.0 / best_a["price"]) / implied_sum, 2)
                    stake_b = round(total_stake * (1.0 / best_b["price"]) / implied_sum, 2)
                    
                    arbs.append({
                        "event": f"{event.get('home_team', '?')} vs {event.get('away_team', '?')}",
                        "sport": event.get("sport_title", ""),
                        "market": f"{market_type} @ {point}",
                        "profit_pct": round(profit_pct, 3),
                        "implied_sum": round(implied_sum, 5),
                        "bets": [
                            {"outcome": side_a, "book": best_a["book"], "odds": best_a["price"], "stake": stake_a, "line": point},
                            {"outcome": side_b, "book": best_b["book"], "odds": best_b["price"], "stake": stake_b, "line": point},
                        ],
                        "total_stake": total_stake,
                        "guaranteed_return": round(total_stake / implied_sum, 2),
                        "guaranteed_profit": round(total_stake / implied_sum - total_stake, 2),
                    })
    
    return sorted(arbs, key=lambda x: -x["profit_pct"])


# ─── Display ──────────────────────────────────────────────────────────────────

def display_arbs(arbs: list, title: str = "Arbitrage Opportunities"):
    """Pretty-print arbitrage opportunities."""
    if not arbs:
        print(f"\n  No {title.lower()} found.\n")
        return
    
    print(f"\n{'='*70}")
    print(f"  {title} — {len(arbs)} found")
    print(f"{'='*70}")
    
    for i, arb in enumerate(arbs, 1):
        print(f"\n  ┌─ #{i}  {arb['event']}")
        print(f"  │  Sport: {arb['sport']}")
        if "market" in arb:
            print(f"  │  Market: {arb['market']}")
        print(f"  │  Profit: {arb['profit_pct']:.3f}%  (implied sum: {arb['implied_sum']:.5f})")
        print(f"  │")
        
        bet_table = []
        for bet in arb["bets"]:
            bet_table.append([
                bet["outcome"],
                bet["book"],
                f"{bet['odds']:.2f}",
                f"${bet['stake']:.2f}",
            ])
        
        print(tabulate(
            bet_table,
            headers=["Outcome", "Bookmaker", "Odds", "Stake"],
            tablefmt="simple",
            stralign="left",
        ).replace("\n", "\n  │  "))
        
        print(f"\n  │  Total stake: ${arb['total_stake']:.2f}")
        print(f"  │  Guaranteed return: ${arb['guaranteed_return']:.2f}")
        print(f"  │  Guaranteed profit: ${arb['guaranteed_profit']:.2f}")
        print(f"  └{'─'*60}")
    
    print()


def display_odds_comparison(events: list, max_events: int = 10):
    """Show a side-by-side odds comparison table for events."""
    print(f"\n{'='*70}")
    print(f"  Odds Comparison (showing up to {max_events} events)")
    print(f"{'='*70}\n")
    
    for event in events[:max_events]:
        print(f"  {event.get('home_team', '?')} vs {event.get('away_team', '?')}")
        commence = event.get("commence_time", "")
        if commence:
            try:
                dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                print(f"  Starts: {dt.strftime('%a %d %b %Y %H:%M %Z')}")
            except:
                print(f"  Starts: {commence}")
        
        rows = []
        for bm in event.get("bookmakers", []):
            bm_name = TARGET_BOOKS.get(bm["key"], bm["key"])
            for market in bm.get("markets", []):
                if market["key"] == "h2h":
                    odds_str = "  |  ".join(
                        f"{o['name']}: {o['price']:.2f}" for o in market["outcomes"]
                    )
                    rows.append([bm_name, odds_str])
        
        if rows:
            print(tabulate(rows, headers=["Book", "Odds"], tablefmt="simple", stralign="left"))
        else:
            print("  No odds available from target books.")
        print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def scan_sport(api_key: str, sport_key: str, sport_name: str, threshold: float, show_odds: bool):
    """Scan a single sport for arb opportunities."""
    print(f"\n{'─'*70}")
    print(f"  Scanning: {sport_name} ({sport_key})")
    print(f"{'─'*70}")
    
    # H2H (moneyline)
    try:
        events = get_odds(api_key, sport_key, markets="h2h")
        print(f"  Found {len(events)} events with h2h odds")
        
        if show_odds and events:
            display_odds_comparison(events)
        
        h2h_arbs = find_h2h_arbs(events, threshold)
        display_arbs(h2h_arbs, f"H2H Arbs — {sport_name}")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  Sport '{sport_key}' not currently available (no upcoming events)")
        elif e.response.status_code == 401:
            print(f"  Invalid API key!")
        else:
            print(f"  HTTP Error: {e}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []
    
    # Spreads
    try:
        spread_events = get_odds(api_key, sport_key, markets="spreads")
        spread_arbs = find_spread_total_arbs(spread_events, "spreads", threshold)
        display_arbs(spread_arbs, f"Spread Arbs — {sport_name}")
    except:
        pass
    
    # Totals
    try:
        total_events = get_odds(api_key, sport_key, markets="totals")
        total_arbs = find_spread_total_arbs(total_events, "totals", threshold)
        display_arbs(total_arbs, f"Totals Arbs — {sport_name}")
    except:
        pass
    
    return h2h_arbs


def main():
    parser = argparse.ArgumentParser(
        description="Arbitrage scanner for Sportsbet, Ladbrokes & SwiftBet via The Odds API"
    )
    parser.add_argument("--key", required=True, help="Your Odds API key")
    parser.add_argument("--sport", default=None, help=f"Sport key (e.g. aussierules_afl). Options: {', '.join(SPORTS.keys())}")
    parser.add_argument("--all-sports", action="store_true", help="Scan all known sports (uses many API requests)")
    parser.add_argument("--threshold", type=float, default=0.0, help="Min profit %% to report (default: 0.0)")
    parser.add_argument("--show-odds", action="store_true", help="Show full odds comparison tables")
    parser.add_argument("--list-sports", action="store_true", help="List all available sports from the API")
    parser.add_argument("--list-books", action="store_true", help="List available Aussie bookmakers")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  ARB SCANNER — Sportsbet / Ladbrokes / SwiftBet")
    print(f"  Target books: {', '.join(TARGET_BOOKS.values())}")
    print(f"  Threshold: {args.threshold}% profit")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # List available sports
    if args.list_sports:
        print("\nFetching available sports...")
        sports = get_available_sports(args.key)
        rows = [[s["key"], s["title"], s["group"], "✓" if s["active"] else ""] for s in sports]
        print(tabulate(rows, headers=["Key", "Title", "Group", "Active"], tablefmt="simple"))
        return
    
    # List target books
    if args.list_books:
        print("\nConfigured target bookmakers:")
        for key, name in TARGET_BOOKS.items():
            print(f"  {key:20s} → {name}")
        print("\nTo add/remove books, edit the TARGET_BOOKS dict in the script.")
        return
    
    # Scan
    all_arbs = []
    
    if args.all_sports:
        for sport_key, sport_name in SPORTS.items():
            arbs = scan_sport(args.key, sport_key, sport_name, args.threshold, args.show_odds)
            all_arbs.extend(arbs)
    elif args.sport:
        sport_name = SPORTS.get(args.sport, args.sport)
        arbs = scan_sport(args.key, args.sport, sport_name, args.threshold, args.show_odds)
        all_arbs.extend(arbs)
    else:
        # Default: scan AFL + NRL (most popular Aussie sports)
        for sport_key in ["aussierules_afl", "rugbyleague_nrl"]:
            sport_name = SPORTS.get(sport_key, sport_key)
            arbs = scan_sport(args.key, sport_key, sport_name, args.threshold, args.show_odds)
            all_arbs.extend(arbs)
    
    # Summary
    print("\n" + "="*70)
    print(f"  SCAN COMPLETE — {len(all_arbs)} total arb opportunities found")
    if all_arbs:
        best = all_arbs[0]
        print(f"  Best: {best['event']} @ {best['profit_pct']:.3f}% profit")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
