from __future__ import annotations

import logging

from fpl_ai.api.client import DataError, FPLClient

LOG = logging.getLogger(__name__)


def ingest(client: FPLClient, *, histories: bool = False, limit: int | None = None) -> dict:
    bootstrap = client.bootstrap(refresh=True)
    fixtures = client.fixtures(refresh=True)
    errors = []
    count = 0
    if histories:
        for player in sorted(bootstrap["elements"], key=lambda p: p["id"])[:limit]:
            try:
                client.player(player["id"])
                count += 1
            except DataError as exc:
                errors.append({"id": player["id"], "error": str(exc)})
                LOG.error("%s", exc)
    return {
        "players": len(bootstrap["elements"]),
        "fixtures": len(fixtures),
        "histories": count,
        "errors": errors,
    }
