# Sources, timestamps and reviewed rules

Checked 2026-10-29 using HTTPS with certificate verification. The official site is
client rendered; `/help/rules` returned an HTML shell, then its public JS rules
chunk supplied the actual text. The bootstrap `game_config` supplied scoring
weights, positional requirements and transfer/club limits. URLs, byte lengths and
SHA256 evidence are in [source-verification.json](source-verification.json).
Full upstream responses and rule bundles remain ignored local research data.

| Official path under https://fantasy.premierleague.com | Observed | Use |
|---|---|---|
| `/api/bootstrap-static/` | 200, 669 players | Players, clubs, events, news, ownership, price, settings, chips, scoring |
| `/api/fixtures/` | 200, 380 fixtures | Schedule, home/away, FDR, results |
| `/api/element-summary/1/` | 200 | Per-fixture player history, upcoming fixtures, season aggregates |
| `/api/entry/1/` | 200 | Example public entry, past-deadline value/bank; no private transfer state |
| `/api/entry/1/event/8/picks/` | 200 | Past-deadline squad, multipliers, autosubs and event summary |
| `/api/event/8/live/` | 200 | Points and scoring-event statistics, finalized only after checking |
| `/api/entry/{id}/history/` | 200 in dashboard smoke | Public gameweek history; no account authentication |
| `/api/game-settings/` | 404 | Rejected guess; not used by application |

The endpoints are publicly accessible but not a supported contractual API. No
published numeric quota or SLA was established. Use sequential requests, a 0.4s
minimum gap, cached histories and bounded retries. HTTP 429 respects Retry-After
seconds; cooldowns over 60s stop the run rather than retrying early. No authenticated
pages, passwords, cookies, write methods or transfer endpoints are implemented.

## Actual data fields and missingness

Raw JSON preserves source attributes including history points, minutes, starts,
goals, assists, clean sheets, conceded, saves, cards, bonus/BPS, xG/xA/xGI/xGC,
ICT, CBI, tackles/recoveries and defensive contribution where provided. Bootstrap
preserves ownership, transfers, status/news, current cost and price-change fields,
and set-piece orders. Presence does not imply every field is validated for predictive
use. The first observed team table has zero match aggregates in several fields;
these are not used as reliable team-strength predictors.

Do not treat model estimates, upstream price projections, imputed features or an
availability heuristic as measured statistics. `NaN` stays missing in exported
rankings. Training imputes feature medians fitted on training only. Labels and
required event-simulation fields cannot be missing. A new player may have no usable
history; do not fill it with another player's invented past.

All snapshots have an actual UTC `fetched_at`, source endpoint and content hash.
The snapshot time is NOT the match kickoff or the time a historical statistic first
became available. A 3h post-kickoff cutoff is a conservative reconstruction proxy,
not proof that later corrected outcomes were available then. Historical data must
not be relabeled with an earlier collection time. For faithful backtesting, collect
before deadlines now, and acquire older archives only with provenance and legitimate
usage rights. `history_past` is a season aggregate, not a full historical GW archive.

## Reviewed 2026/27 rules

From the official rules text and matching bootstrap:

- Fifteen players: 2 GKP, 5 DEF, 5 MID, 3 FWD; initial £100m; max 3 per club.
- Starting XI: 1 GKP, 3–5 DEF, 2–5 MID, 1–3 FWD; select a captain and vice.
- A captain doubles; vice takes over only when captain does not play. If neither
  participates, no bonus. Reserve goalkeeper substitutes only the goalkeeper;
  outfield bench priority respects formation.
- One new free transfer/week, accumulation capped at five; an extra costs four points.
  Wildcard/Free Hit preserve the pre-chip free-transfer count rather than incrementing it.
  The normal per-week transfer cap is read from bootstrap (observed 20).
- Selling price retains half the rise rounded down to £0.1m; falls are fully reflected.
- Two instance windows per named chip were observed: first through GW19, second
  GW20–38. Wildcard and Free Hit open GW2, team chips GW1. Availability belongs to
  the account and must be confirmed manually. One chip can be played/week and Free
  Hit cannot be used in consecutive weeks.
- Appearance: 1 below 60 minutes, 2 at 60+; goals GKP10/DEF6/MID5/FWD4; assist3;
  clean sheet GKP4/DEF4/MID1/FWD0 at 60+; GKP1 per3 saves; GKP/DEF lose1 per2
  conceded. Penalty save5, penalty miss−2, yellow−1, red−3, own goal−2; bonus uses
  official weights and empirical historical bonus, not a reconstructed BPS contest.
- Defensive contribution gives 2 once per fixture: DEF CBI+tackles >=10;
  MID/FWD CBI+tackles+recoveries >=12. It does not stack per threshold multiple.

Weights and windows come from live configuration; 60-minute/save/concession/
defensive thresholds, hit cost and chip transfer-retention semantics come from the
reviewed rule text. `Rules.from_bootstrap` refuses unknown seasons. Event-level rule
or scoring overrides require explicit review (`validate_event`); do not silently
apply ordinary rules to an exceptional event. New entrants' unlimited initial
transfers, possible special midseason transfer grants, detailed red-card concession
rules, exact assist adjudication and BPS ties are not fully simulated by the event
forecast. Its distributions are approximations, not a perfect recreation of official
match scoring.

## Collection operations

```
fpl-ai refresh
fpl-ai refresh --histories
fpl-ai collect --event 8
```

`collect` forces fresh bootstrap/fixtures and retrieves live results; call after
`data_checked` is true for finalized benchmarking. `refresh` saves a new bootstrap
and fixture snapshot; histories respect TTL and resume from cache. A pre-deadline
snapshot collected within 24h is required by the historical benchmark. Missing,
stale or post-deadline inputs fail clearly, rather than being backfilled from today.
The SQLite file can contain public entry names/league metadata if you request an
entry; keep it local. No data are included in the source archive.

## Rights

The official terms were inspected, including restrictions on commercial exploitation
of information from the game. This is personal research code; public access alone
does not grant a data redistribution/commercial license. No third-party statistics
source has been integrated or assumed licensed. Get source permission where needed;
acknowledge the official source and do not commit raw football data under MIT.
