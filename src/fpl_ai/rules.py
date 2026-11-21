"""Season metadata from bootstrap plus explicitly reviewed rule-text constants."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    season: str
    squad: dict[int, int]
    min_play: dict[int, int]
    max_play: dict[int, int]
    club_limit: int
    budget: int
    free_transfer_cap: int
    transfer_cap: int
    chips: tuple[dict, ...]
    scoring: dict
    hit_cost: int = 4

    @classmethod
    def from_bootstrap(cls, bootstrap: dict) -> Rules:
        config = bootstrap["game_config"]
        url = config["settings"]["static_content_url"]
        season = url.rstrip("/").rsplit("/", 1)[-1]
        # Constants (thresholds/hits/FT chip retention) reviewed only for this season.
        if season != "2026_27":
            raise ValueError(f"Rules for {season} need review; refusing to apply 2026/27 constants")
        r = config["rules"]
        types = bootstrap["element_types"]
        if r["squad_squadsize"] != 15 or r["squad_squadplay"] != 11:
            raise ValueError("Unsupported squad/lineup size")
        return cls(
            season,
            {t["id"]: t["squad_select"] for t in types},
            {t["id"]: t["squad_min_play"] for t in types},
            {t["id"]: t["squad_max_play"] for t in types},
            r["squad_team_limit"],
            r["squad_total_spend"],
            1 + r["max_extra_free_transfers"],
            r["transfers_cap"],
            tuple(bootstrap["chips"]),
            config["scoring"],
        )

    def next_free_transfers(self, free: int, used: int, chip: str | None = None) -> int:
        if not 0 <= free <= self.free_transfer_cap or used < 0:
            raise ValueError("Invalid free-transfer state")
        if chip in ("wildcard", "freehit"):
            return free  # Official text: saved transfers retained, not incremented.
        return min(self.free_transfer_cap, max(0, free - used) + 1)

    def chip_allowed(
        self, name: str, event: int, available_ids: set[int], previous_chip: str | None = None
    ) -> bool:
        return not (name == "freehit" and previous_chip == "freehit") and any(
            c["name"] == name
            and c["id"] in available_ids
            and c["start_event"] <= event <= c["stop_event"]
            for c in self.chips
        )

    def validate_event(self, event: dict) -> None:
        overrides = event.get("overrides", {})
        if (
            any(overrides.get(k) for k in ("rules", "scoring", "element_types"))
            or overrides.get("pick_multiplier") is not None
        ):
            raise ValueError(
                f"GW {event['id']} has special rule overrides requiring explicit review"
            )
