# Playing styles and two-name connection — v0.3.0

This is an **app-only Windows update under 8 MB**. Close the previous FPL Manager console,
then extract this ZIP to a temporary folder. Copy the **contents** of its `fpl-ai-manager`
folder into your existing `fpl-ai-manager` folder, merging folders and replacing included application files. Keep your existing `data/` and `models/` folders. Neither is bundled
or replaced. Run `RUN_FPL_MANAGER.bat`; the health endpoint should show version `0.3.0`.

## Choose how to play

The playing-style buttons appear on Overview, My team, Players, Transfers, Captaincy and
New team builder. New installations/defaults use **Aggressive**. Your choice persists locally.

- **Aggressive:** favors recent high-return potential, weighted by predicted minutes.
- **Balanced:** maximizes the model's expected points.
- **Conservative:** penalizes recent downside and favors steadier returns.

The chosen score controls the MILP squad/transfer objective, starting XI, captain, vice-captain,
bench order and player rankings across the selected horizon. Transfer hits still cost four
points each; budget, selling prices, positions, club limits and chip constraints still apply.
Changing style clears old recommendations so they cannot be mistaken for the new choice.

Projected points remain the fitted model's means. A larger aggressive **style score** is not
extra expected FPL points. This update changes decision preferences, not model calibration.
It does not contain a newly trained model or evidence of improved future scores.

The preference uses only up to ten completed prior-gameweek fixture results. Historical
85th/15th percentile spreads around the historical mean are shrunk by `n/(n+5)` and weighted
by `0.65`; the aggressive bonus is also weighted by predicted minutes/90. The adjustment
scales with the square root of the number of fixtures; blanks score zero. Fewer than three
history rows receive no adjustment. These are empirical preference proxies, **not calibrated
prediction intervals**. Sparse players can remain identical between styles. No extra credit
is given simply for low ownership. Check current injuries before selecting any recommendation.

## Connect using team name and manager name only

The two input fields are **FPL team name** and **Manager name** (the full public name on FPL).
There is no league-link or numeric-ID input. FPL does not provide a global search for these
names. A first connection therefore verifies the account through your official signed-in tab:

1. In Chrome open `chrome://extensions`, or Edge `edge://extensions`.
2. Enable **Developer mode**, choose **Load unpacked**, and select the included
   `browser-connector` folder inside your installation. Pin **FPL Manager Local Connector**.
3. In the local app's Settings or My team, enter both names and click **Connect my team**.
4. The official FPL website opens. Sign in **only on the official FPL site** if needed.
   On that tab click the pinned connector, then **Verify my account**.
5. Return to the local app. It verifies both names using public FPL metadata and loads your
   public last-deadline squad automatically. Confirm later transfers and your private finances.

The helper captures a five-minute pairing link before the official site's router runs. If login
opens a different tab or the connection expires, return to the local app and click Connect again.
If a pop-up is blocked, use the **Open official FPL** link shown in the connection message.
Keep the local manager running and its connection page open while pairing.

The helper reads only the `player.entry` reference from `/api/me/` inside the official tab.
It sends only that public reference and a one-use random pairing token to your loopback app.
Passwords, cookies, email and the full account response are not sent to the app. It does not
make transfers or obtain live private squad/bank/selling-price data. Public picks reflect the last
deadline, and FPL may not publish picks before your first deadline.

Verified name/reference pairs are remembered locally in `data/account-connections.json`.
Existing browser references are preserved and checked against **both names** on reconnect.
Your browser still stores your squad, selling prices and bank; account changes clear stale financial
confirmation. The legacy Streamlit UI can reuse the same verified local registry; first verification
is performed in the Rust app. Manual selection of 15 players remains available without the helper.

## Verification and limits

Python and Rust automated checks plus desktop/mobile browser regression results are recorded in
`docs/PLAYING_STYLE_VERIFICATION.md`. The helper protocol is tested with offline fixtures.
A real signed-in FPL session was not available for end-to-end testing. The Windows executable
is cross-compiled; it was not executed on a Windows PC here. Browser tests run against Linux Rust.
Existing trained model inference is retained, with no accuracy claim from the strategy change.

See `docs/PLAYING_STYLE_FILES.md` for the exact created/modified file list and ZIP contents.
