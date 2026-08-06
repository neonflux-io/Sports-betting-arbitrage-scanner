"""Thin client for The Odds API."""

from __future__ import annotations

from typing import Any

import requests

from arb_scanner.config import BASE_URL


class OddsAPIError(Exception):
    """Raised when The Odds API returns an error response."""


class OddsAPIClient:
    """Minimal wrapper around The Odds API v4 endpoints used by the scanner."""

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()
        self.last_quota: dict[str, str] = {}

    def get_sports(self) -> list[dict[str, Any]]:
        """Return all sports currently available from the API."""
        return self._get(BASE_URL)

    def get_odds(self, sport: str, markets: str = "h2h") -> list[dict[str, Any]]:
        """
        Fetch event odds for a sport.

        Each successful call typically consumes 1 request against monthly quota
        (see The Odds API pricing/docs for exact billing rules).
        """
        params = {
            "regions": "au",
            "markets": markets,
            "oddsFormat": "decimal",
        }
        return self._get(f"{BASE_URL}/{sport}/odds", params=params)

    def _get(self, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = {"apiKey": self.api_key, **(params or {})}
        try:
            response = self.session.get(url, params=query, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 401:
                raise OddsAPIError("Invalid API key.") from exc
            if status == 404:
                raise OddsAPIError("Sport not currently available (no upcoming events).") from exc
            if status == 429:
                raise OddsAPIError("API rate limit or quota exceeded.") from exc
            raise OddsAPIError(f"HTTP error from Odds API: {exc}") from exc
        except requests.RequestException as exc:
            raise OddsAPIError(f"Network error contacting Odds API: {exc}") from exc

        self.last_quota = {
            "used": response.headers.get("x-requests-used", "?"),
            "remaining": response.headers.get("x-requests-remaining", "?"),
        }
        data = response.json()
        if not isinstance(data, list):
            raise OddsAPIError("Unexpected API payload shape (expected a list).")
        return data
