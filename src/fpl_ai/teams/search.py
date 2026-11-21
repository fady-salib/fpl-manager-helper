"""Scoped public classic-league search; never pretend a global name search exists."""

from urllib.parse import urlparse


def normalise(value):
    return " ".join(str(value).split()).lower()


def validate_name(value):
    value = " ".join(str(value).split())
    if not value or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise ValueError("Enter your FPL team name (1–80 characters).")
    return value


def league_id(value):
    try:
        url = urlparse(str(value).strip())
        if (
            url.scheme != "https"
            or url.hostname != "fantasy.premierleague.com"
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise ValueError(
                "Use an HTTPS public classic league link on fantasy.premierleague.com."
            )
        parts = [p for p in url.path.split("/") if p]
        if len(parts) != 4 or parts[0] != "leagues" or parts[2:] != ["standings", "c"]:
            raise ValueError("Use a public classic mini-league link ending /leagues/…/standings/c.")
        result = int(parts[1])
        if not 1 <= result <= 1_000_000_000:
            raise ValueError("Invalid classic league reference")
        return result
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Paste a public classic mini-league link from your FPL Leagues page; invitation codes and head-to-head links are not supported."
        ) from exc


def search_teams(client, name, league_url="", *, page=1, known_entry_id=None):
    name = validate_name(name)
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 10000:
        raise ValueError("Invalid league search page")
    league = league_id(league_url) if league_url.strip() else None
    if known_entry_id and page == 1:
        try:
            entry = client.entry(int(known_entry_id))
            if normalise(entry.get("name", "")) == normalise(name):
                manager = " ".join(
                    str(entry.get(k) or "") for k in ("player_first_name", "player_last_name")
                ).strip()
                return {
                    "query": name,
                    "league": "Saved connection",
                    "candidates": [
                        {
                            "reference": int(known_entry_id),
                            "name": entry["name"],
                            "manager": manager or "Connected manager",
                            "rank": entry.get("summary_overall_rank"),
                            "exact": True,
                        }
                    ],
                    "scanned": 1,
                    "next_page": None,
                    "complete": True,
                    "saved_connection": True,
                }
        except (RuntimeError, ValueError):
            if league is None:
                raise ValueError(
                    "The saved connection could not be verified. Add a public classic mini-league link to search again."
                ) from None
    if league is None:
        raise ValueError(
            "FPL has no global team-name search. For a first lookup, paste a public classic mini-league link, or select your squad manually. No team ID is required."
        )
    matches = {}
    scanned = 0
    next_page = None
    league_name = "Public mini-league"
    for current in range(page, page + 2):
        result = client.league_standings(league, current)
        standings = result.get("standings", {})
        rows = standings.get("results")
        if not isinstance(rows, list) or not isinstance(standings.get("has_next"), bool):
            raise ValueError("This league does not expose valid public classic standings.")
        league_name = result.get("league", {}).get("name") or league_name
        scanned += len(rows)
        for row in rows:
            reference, entry_name = row.get("entry"), row.get("entry_name")
            if (
                not isinstance(reference, int)
                or isinstance(reference, bool)
                or reference < 1
                or not isinstance(entry_name, str)
            ):
                continue
            folded = normalise(entry_name)
            if normalise(name) in folded:
                matches[reference] = {
                    "reference": reference,
                    "name": entry_name,
                    "manager": row.get("player_name") or "Manager name unavailable",
                    "rank": row.get("rank"),
                    "exact": folded == normalise(name),
                }
        next_page = current + 1 if standings["has_next"] else None
        if next_page is None:
            break
    return {
        "query": name,
        "league": league_name,
        "candidates": sorted(
            matches.values(),
            key=lambda c: (
                not c["exact"],
                c["rank"] if c["rank"] is not None else float("inf"),
                c["reference"],
            ),
        ),
        "scanned": scanned,
        "next_page": next_page,
        "complete": next_page is None,
        "saved_connection": False,
    }
