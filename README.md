# Venue Map

Prepared by Josh Torney.

Interactive map of licensed venues for prospecting, centred on Geelong and surrounds, plus a route planner for the weekly run.

## Files

- `index.html` - the map
- `route.html` - the route planner: route days, today's run stop by stop in Waze, visit log, follow-ups and calendar export
- `locations.json` - every venue on the map (name, address, type, status, liquor licence, priority, route day)
- `suburbs.geojson` - suburb boundaries for the map (Geelong region, Ballarat, Daylesford and every suburb with a venue)
- `manifest.webmanifest`, `sw.js`, `icon-*.png` - let the route planner install as an app on a phone and work without signal

## Updating venues

Status changes, notes and new venues save in your browser first. To make them permanent:

1. Click **Download locations.json** at the bottom of the map's sidebar.
2. Upload it here, replacing the existing `locations.json`.

Status changes made in the route planner on the same device show up in the map's save bar too.

## Data source

Venues come from the Liquor Control Victoria register of current licences (31 August 2026), plus venues added through the map's own search.
