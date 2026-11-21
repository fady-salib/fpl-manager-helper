# Team-name lookup — v0.2.1 verification

The previous user-facing numeric FPL team input has been replaced in both the native
Rust UI and the preserved Streamlit UI with a team-name lookup and explicit manager
selection. Numeric entry references remain internal to FPL API calls; deleting those
references would make squad retrieval impossible.

## Public API boundary

The public API has no global team-name lookup and names are not unique. The first lookup
uses a user-supplied public classic mini-league URL. The app constructs only the fixed
`leagues-classic/<reference>/standings/?page_standings=<page>` endpoint on the official
FPL domain, and never fetches the supplied URL directly. Other hosts, HTTP, head-to-head
paths, invitation codes and malformed scopes are rejected. Two pages are checked per
explicit action; partial results are labeled and continuation is manual. Empty results
are not misrepresented as an exhaustive global no-match.

## Implemented behavior

- Case-insensitive, whitespace-normalized name matching in the supplied standings.
- Same-name managers remain separate results, with name, manager and league rank shown.
- No automatic selection/loading of the first same-name result.
- Background native search jobs, five-minute bounded in-memory page cache, cached saved
  connection checks, and no network activity caused merely by navigating pages.
- Current entry name verified again before picks are returned. A renamed result clears
  the search cache and does not overwrite the existing squad or financial inputs.
- Older browser state and JSON backups migrate `team_id` into an internal
  `team_reference`. Existing financial values are preserved by the upgrade.
- Successful account switches reset financial confirmation/selling prices and invalidate
  old lineup/transfer plans. Superseded lookup/solve results do not replace a newer team.
- Manual local team naming and existing 15-player selection remain available when no
  public mini-league can be used. This path is explicitly not an official squad download.
- Updated Windows launcher detects an older running server and missing models/data. The
  patch contains application files only; existing resources must be retained.

## Checks actually performed

- **114 Python tests passed**, including league URL allowlisting, duplicate identities,
  bounded pagination, cached pages, saved-name verification and legacy UI regressions.
- **19 Rust tests passed**, including seven new name/scope/result tests and the existing
  model, leakage and optimization constraint tests.
- Rust formatting, Clippy with all targets/warnings denied, Python Ruff formatting/lint,
  Python compilation and JavaScript syntax checks passed.
- Native search queried two real public Overall standings pages (100 entries) using a
  deliberately non-matching test query. It returned a partial result with next page 3
  in about 1.25 seconds. No manager entry or picks endpoint was queried in this live
  API test. No public manager records were saved to a delivery artifact.
- Chromium browser tests passed for missing-scope guidance, duplicate manager choices,
  manual pagination with accumulated results, explicit squad choice, native lineup
  solving, saved reference reuse, rename rejection, old-state financial preservation,
  and desktop/390px mobile layout. Public lookup responses and manager names in this
  browser test were mocked; the native player pool and lineup solver were real.
- New Linux and x64 Windows executables were built. The Windows executable is
  cross-compiled and system-DLL checked; native Windows execution remains untested.

Raw evidence: `reports/team-name-browser-results.json`, `team-name-api-smoke.json`,
`team-name-python-tests.txt`, `team-name-rust-tests.txt`, `team-name-clippy.txt`.
The update does not change model predictions, trained artifacts, data preparation,
optimization rules or user datasets. No commits or pushes were performed.
