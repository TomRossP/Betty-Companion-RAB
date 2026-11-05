# Betty Companion RAB

The Request A Bet edition of Betty Companion: everything Betty Companion 1.2.25 does, plus the pink Request A Bet
wagers from the website, racing and (`RAB_SPORTS=1`) sports. Versioned on its own from 1.0.0; see [CHANGELOG.md](CHANGELOG.md).

Works through Betty's unedited wagers on a shop till. It reads each slip, checks it against Betty's racecards and
enters it. In LIVE mode it places the wager; in TEST mode it stops just before placing. Anything it can't do is left
for staff, with the reason.

## On a till

1. Download `BettyCompanionRAB-<version>.zip` from **Releases** and unzip it somewhere the till can write to, for example
   `C:\BettyCompanion`.
2. Double-click `BettyCompanion.exe`. Nothing is installed.
3. Pair the till with the relay once: **Controls** tab, **Pair this till**, then approve the code on the relay's
   `/admin` page.

The staff guide is [release/README.txt](release/README.txt). The relay is set up as in
[relay/RELAY_SETUP.md](relay/RELAY_SETUP.md).

## For development

- `betty_companion.py`: the program. `python betty_companion.py` runs it on its own.
- `launcher.py`: the control window (`BettyCompanion.exe`). It runs the program with `--backend`.
- `relay_link.py`: pairing with the relay. `error_guide.py`: the explanations shown in the Errors tab.
- `master_index.py`: Betty's Master Index, how sports selections are entered: which row fits, whether a list can be believed.
  `sports_markets.json` has the market names, `index_price_glyphs.json` the price column's exact shapes.
- `rab_rules.py`: Request A Bet (the pink wagers from the website): reads the typed request and the customer's account
  notes. The notes shorthand is in `rab_notes_dictionary.json`; a note it doesn't cover means the request is skipped.
- `python build_release.py`: builds `dist\BettyCompanion\` and the release zip. Needs PyInstaller and Tesseract
  installed on the build PC.
- Per-PC settings and keys go in `.env`, which is never committed. See [CHANGELOG.md](CHANGELOG.md) for every release.
