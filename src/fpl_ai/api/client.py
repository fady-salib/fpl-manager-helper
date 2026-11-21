"""Public GET endpoints only. No passwords, private cookies or transfer execution."""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from fpl_ai.storage import SnapshotStore

LOG = logging.getLogger(__name__)


class DataError(RuntimeError):
    """Unavailable, invalid or incompatible upstream data."""


def validate(endpoint: str, data: Any) -> None:
    if endpoint == "bootstrap-static/":
        if not isinstance(data, dict) or not all(
            isinstance(data.get(k), list) and data[k]
            for k in ("elements", "teams", "events", "element_types")
        ):
            raise DataError("Bootstrap schema missing required lists")
        ids = [p.get("id") for p in data["elements"]]
        if len(set(ids)) != len(ids) or any(
            isinstance(i, bool) or not isinstance(i, int) or i < 1 for i in ids
        ):
            raise DataError("Invalid/duplicate player IDs")
        for p in data["elements"]:
            if not all(k in p for k in ("team", "element_type", "now_cost", "web_name")):
                raise DataError("Incomplete player record")
    elif endpoint == "fixtures/":
        if not isinstance(data, list) or any(
            not isinstance(f, dict) or not {"id", "team_h", "team_a", "event"} <= f.keys()
            for f in data
        ):
            raise DataError("Invalid fixture records")
    elif endpoint.startswith("element-summary/"):
        if not isinstance(data, dict) or not isinstance(data.get("history"), list):
            raise DataError("Invalid player history")
        for row in data["history"]:
            if (
                not isinstance(row, dict)
                or not {"fixture", "round", "kickoff_time", "minutes", "total_points"} <= row.keys()
            ):
                raise DataError("Incomplete match-history record")
            if not isinstance(row["round"], int) or row["round"] < 1:
                raise DataError("Invalid history gameweek")
            for stat in ("minutes", "total_points"):
                try:
                    valid = math.isfinite(float(row[stat]))
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    raise DataError(f"Invalid history {stat}")
    elif endpoint.startswith("leagues-classic/"):
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("standings"), dict)
            or not isinstance(data["standings"].get("results"), list)
            or not isinstance(data["standings"].get("has_next"), bool)
        ):
            raise DataError("Invalid public league standings")
    elif not isinstance(data, dict):
        raise DataError("Expected an API object")


class FPLClient:
    BASE = "https://fantasy.premierleague.com/api/"

    def __init__(
        self,
        store: SnapshotStore | None = None,
        *,
        ttl: int = 900,
        interval: float = 0.4,
        retries: int = 3,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.store = store or SnapshotStore()
        self.ttl = ttl
        self.interval = interval
        self.retries = retries
        self.last_request = 0.0
        self.http = httpx.Client(
            base_url=self.BASE,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "FPL-AI-Manager/0.1 public-data research"},
        )

    def __enter__(self) -> FPLClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def get(self, endpoint: str, *, refresh: bool = False) -> Any:
        # Fixed domain plus relative endpoint: never allow caller-provided URLs.
        allowed = r"(?:bootstrap-static|fixtures|element-summary/[1-9][0-9]*|entry/[1-9][0-9]*(?:/history|/event/[1-9][0-9]*/picks)?|event/[1-9][0-9]*/live)/"
        league_endpoint = r"leagues-classic/[1-9][0-9]*/standings/\?page_standings=[1-9][0-9]*"
        if not (re.fullmatch(allowed, endpoint) or re.fullmatch(league_endpoint, endpoint)):
            raise ValueError("Unsupported public API endpoint")
        cached = self.store.latest(endpoint)
        if cached and not refresh and (datetime.now(UTC) - cached[0]).total_seconds() < self.ttl:
            validate(endpoint, cached[1])
            return cached[1]
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                r = self.http.get(endpoint)
                if r.status_code == 429 or r.status_code >= 500:
                    delay = r.headers.get("Retry-After", "")
                    try:
                        wait = float(delay)
                    except ValueError:
                        try:
                            wait = (
                                parsedate_to_datetime(delay) - datetime.now(UTC)
                            ).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            wait = 2**attempt
                    if not math.isfinite(wait):
                        wait = 2**attempt
                    if wait > 60:
                        raise DataError(f"API requested {wait:.0f}s cooldown; retry later")
                    if attempt < self.retries:
                        time.sleep(max(1, wait))
                        continue
                r.raise_for_status()
                data = r.json()
                validate(endpoint, data)
                self.store.put(endpoint, data)
                return data
            except (httpx.HTTPError, ValueError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise DataError(f"API {endpoint}: HTTP {exc.response.status_code}") from exc
                if attempt == self.retries:
                    raise DataError(f"API {endpoint} unavailable after retries: {exc}") from exc
                LOG.warning("Retry %s for %s: %s", attempt + 1, endpoint, type(exc).__name__)
                time.sleep(min(60, 2**attempt))
        raise DataError(f"API {endpoint} failed")

    @staticmethod
    def _id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("API IDs must be positive integers")
        return value

    def bootstrap(self, *, refresh: bool = False) -> dict:
        return self.get("bootstrap-static/", refresh=refresh)

    def fixtures(self, *, refresh: bool = False) -> list[dict]:
        return self.get("fixtures/", refresh=refresh)

    def player(self, player_id: int) -> dict:
        return self.get(f"element-summary/{self._id(player_id)}/")

    def entry(self, team_id: int) -> dict:
        return self.get(f"entry/{self._id(team_id)}/")

    def entry_history(self, team_id: int) -> dict:
        return self.get(f"entry/{self._id(team_id)}/history/")

    def picks(self, team_id: int, gameweek: int) -> dict:
        return self.get(f"entry/{self._id(team_id)}/event/{self._id(gameweek)}/picks/")

    def league_standings(self, league: int, page: int = 1) -> dict:
        if page > 10000:
            raise ValueError("League search page is too large")
        return self.get(
            f"leagues-classic/{self._id(league)}/standings/?page_standings={self._id(page)}"
        )

    def live(self, gameweek: int) -> dict:
        return self.get(f"event/{self._id(gameweek)}/live/")
