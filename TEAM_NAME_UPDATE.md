> Superseded by v0.3.0: see [PLAYING_STYLE_UPDATE.md](PLAYING_STYLE_UPDATE.md). The current UI uses team name and manager name; league links are no longer required. The notes below describe the older v0.2.1 release.

# Team-name connection update — v0.2.1

This is an **app-only update** for your existing Rust FPL Manager installation.
It does not include or replace your models, datasets, snapshot database or private team inputs.

## Install on Windows

1. Close the running FPL Manager console window (or press Ctrl+C in it).
2. Extract the update ZIP into the same parent folder that already contains your
   `fpl-ai-manager` folder. Allow replacement of the included application files.
   The result must be your existing `fpl-ai-manager/bin/fpl-manager.exe`, with your
   existing `data/` and `models/` folders beside it. Do not run the update in isolation.
3. Run `RUN_FPL_MANAGER.bat`. Refresh the browser if an old form is still open.

No model/data parts need to be downloaded again. The launcher detects an old running
server and asks you to close it, instead of opening its outdated team-ID form.

## New connection flow

1. Open **My team** or **Settings**.
2. Enter your **FPL team name**.
3. For a first lookup, paste a **public classic mini-league link** from your FPL Leagues
   tab, such as `https://fantasy.premierleague.com/leagues/123/standings/c`.
4. Click **Find my team**. Choose the matching team **and manager**, then **Load squad**.
5. Confirm your squad changes and financial information in Settings before transfers.

The official public API has **no global team-name search** and team names are **not
unique**. This update searches the supplied public classic league, not every manager.
It checks at most two standings pages per action; **Search next league pages** continues
explicitly. A partial search is labeled, never presented as an exhaustive no-match result.
A small mini-league is usually the easiest and quickest scope. Head-to-head links and
invitation/join codes are not supported by this lookup.

Already connected teams reuse their saved reference internally, after checking their
current name. You never enter a numeric team ID. API references remain internal because
FPL requires them to fetch picks. To choose a different team with the same name, use
**Search the league instead**. Names are checked again before loading; if the team was
renamed, the existing squad is preserved and the search cache is invalidated.

If no public league is available, choose **use this name and select my squad manually**.
This saves a local name and lets you pick 15 players in Settings; it does not pretend
that an official squad was downloaded.

## Compatibility and validation

- Old saved browser connections and JSON backups migrate `team_id` to an internal
  `team_reference`. Existing squad/financial values survive the update.
- A successful switch to another official team clears selling prices, resets financial
  confirmation and invalidates old lineup/transfer results. Failed or superseded lookups
  do not replace the current squad. Official transfers are never executed.
- Both the Rust interface and the preserved Streamlit interface use team-name lookup.
- 114 Python tests and 19 Rust tests passed, with browser checks for duplicate choices,
  explicit pagination, saved connections, rename conflicts, old-state migration and
  desktop/mobile layout. Public classic standings were tested against the official API
  without loading any real manager's picks. Browser manager names use test fixtures.
- The Windows executable is cross-compiled and checked for system-only DLL imports;
  native Windows execution remains untested. The corresponding Linux runtime was tested.

See `docs/TEAM_NAME_FILES.md` for the exact update file list and
`reports/team-name-*.json` for verification. Existing ML accuracy limits are unchanged.
