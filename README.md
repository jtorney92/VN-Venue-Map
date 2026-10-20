# Venue Map

Prepared by Josh Torney.

Interactive map of licensed venues for prospecting, centred on Geelong and surrounds, plus a route planner for the weekly run.

## Files

- `index.html` - the map
- `route.html` - the route planner: route days, today's run stop by stop in Waze, visit log, follow-ups and calendar export
- `locations.json` - every venue on the map (name, address, type, status, liquor licence, priority, route day)
- `suburbs.geojson` - suburb boundaries for the map (Geelong region, Ballarat, Daylesford and every suburb with a venue)
- `manifest.webmanifest`, `sw.js`, `icon-*.png` - let the route planner install as an app on a phone and work without signal
- `tools/refresh_register.py` and `.github/workflows/refresh-register.yml` - the monthly venue refresh from the liquor licence register
- `REGISTER_UPDATES.md` - what each monthly refresh added, removed or flagged

## Updating venues

Status changes, notes and new venues save in your browser first. To make them permanent:

1. Click **Download locations.json** at the bottom of the map's sidebar.
2. Upload it here, replacing the existing `locations.json`.

Status changes made in the route planner on the same device show up in the map's save bar too.

## Data source

Venues come from the Liquor Control Victoria register of current licences (31 August 2026), plus venues added through the map's own search.

## Monthly venue refresh

Every Monday morning GitHub checks data.vic.gov.au for a new Liquor Control Victoria register. When a new month is out it merges it into `locations.json` and pushes, so the map and planner update on their own:

- new licences in Geelong, Surf Coast, Queenscliffe and Golden Plains are added, plus mobile bars anywhere in Victoria
- a venue whose licence is gone is removed if it was never worked; if it has a status or notes it stays, flagged to check
- names, types, priorities, statuses and notes you have set are kept

Each run is written up in `REGISTER_UPDATES.md`. To run it straight away: Actions tab, Monthly venue refresh, Run workflow.
