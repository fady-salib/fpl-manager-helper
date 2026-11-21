"""Realized autosubstitution and captain fallback, including a zero-minute red-card case."""

from __future__ import annotations

from itertools import combinations

from fpl_ai.rules import Rules


def score_lineup(
    starting: list[int],
    bench: list[int],
    captain: int,
    vice: int,
    positions: dict[int, int],
    points: dict[int, float],
    appeared: dict[int, bool],
    rules: Rules,
    *,
    chip: str | None = None,
) -> float:
    """Bench: reserve GK first then ordered three outfield players.

    `appeared` must represent official participation (minutes OR red/yellow card),
    not points!=0: an appearing player can score zero or negative points.
    """
    squad = starting + bench
    if len(starting) != 11 or len(bench) != 4 or len(set(squad)) != 15:
        raise ValueError("Need 11 starters and 4 distinct bench players")
    if captain not in starting or vice not in starting or captain == vice:
        raise ValueError("Captain and vice must be different starters")
    counts = {pos: sum(positions[i] == pos for i in starting) for pos in rules.squad}
    if not all(rules.min_play[p] <= n <= rules.max_play[p] for p, n in counts.items()):
        raise ValueError("Invalid starting formation")
    if positions[bench[0]] != 1 or any(positions[i] == 1 for i in bench[1:]):
        raise ValueError("Reserve goalkeeper must be first bench slot")
    if chip == "bboost":
        selected = squad
    else:
        selected = list(starting)
        keeper = next(i for i in starting if positions[i] == 1)
        if not appeared[keeper] and appeared[bench[0]]:
            selected.remove(keeper)
            selected.append(bench[0])
        missing = [i for i in starting if positions[i] != 1 and not appeared[i]]
        # Highest-priority eligible subset, retaining formation even for unreplaced DNP slots.
        choices = []
        for size in range(min(3, len(missing)) + 1):
            for incoming in combinations([i for i in bench[1:] if appeared[i]], size):
                for outgoing in combinations(missing, size):
                    shape = dict(counts)
                    for i in incoming:
                        shape[positions[i]] += 1
                    for i in outgoing:
                        shape[positions[i]] -= 1
                    if all(rules.min_play[p] <= n <= rules.max_play[p] for p, n in shape.items()):
                        priority = tuple(int(i in incoming) for i in bench[1:])
                        choices.append((priority, incoming, outgoing))
        if choices:
            _, ins, outs = max(choices, key=lambda c: c[0])
            selected = [i for i in selected if i not in outs] + list(ins)
    total = sum(points[i] for i in selected)
    active_cap = captain if appeared[captain] else vice if appeared[vice] else None
    if active_cap is not None:
        total += points[active_cap] * (2 if chip == "3xc" else 1)
    return float(total)
