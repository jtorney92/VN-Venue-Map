# Venue Map

Prepared by Josh Torney.

Interactive map of licensed venues for prospecting, centred on Geelong and surrounds, plus a route planner for the weekly run.

## Files

- `index.html` - the map
- `route.html` - the route planner: route days, today's run stop by stop in Waze, visit log, follow-ups and calendar export
- `locations.json` - every venue on the map (name, address, type, status, liquor licence, priority, route day)
- `suburbs.geojson` - suburb boundaries for the map (Geelong region, Ballarat, Daylesford and every suburb with a venue)
- `hours.js` - reads opening hours (OpenStreetMap's format and the planner's own) for the map and planner
- `google.js` - the only route to Google: the map's Find venues button, off until a key is pasted on a device, and capped
- `manifest.webmanifest`, `sw.js`, `icon-*.png` - let the route planner install as an app on a phone and work without signal
- `tools/refresh_register.py`, `tools/osm_hours.py` and `.github/workflows/refresh-register.yml` - the weekly venue refresh
- `REGISTER_UPDATES.md` - what each monthly register update added, removed or flagged

## Updating venues

Status changes, notes and new venues save in your browser first. To make them permanent:

1. Click **Download locations.json** at the bottom of the map's sidebar.
2. Upload it here, replacing the existing `locations.json`.

Status changes made in the route planner on the same device show up in the map's save bar too.

## Data source

Venues come from the Liquor Control Victoria register of current licences (31 August 2026), plus venues added through the map's own search.

## Weekly venue refresh

Every Monday morning GitHub checks data.vic.gov.au for a new Liquor Control Victoria register. When a new month is out it merges it into `locations.json` and pushes, so the map and planner update on their own:

- new licences in Geelong, Surf Coast, Queenscliffe and Golden Plains are added, plus mobile bars anywhere in Victoria
- a venue whose licence is gone is removed if it was never worked; if it has a status or notes it stays, flagged to check
- names, types, priorities, statuses and notes you have set are kept

Each register update is written up in `REGISTER_UPDATES.md`.

The same job pulls opening hours from OpenStreetMap for every venue it can match by name, type and distance, and stores them in each venue's `oh` field. It's free and uses no key. Hours you note in the route planner are kept on your phone (and in its backup) and take priority over OpenStreetMap's.

To run it straight away: Actions tab, Weekly venue refresh, Run workflow.

## Google

Nothing in the repo holds a Google key. The map's Find venues button only works on a device where a key has been pasted (it's kept in that browser), and it stops itself at 300 searches a month per device, well inside Google's free 1,000. The route planner never calls Google.

Opening hours data © OpenStreetMap contributors, available under the Open Database Licence.
