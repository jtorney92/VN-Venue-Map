#!/usr/bin/env python3
"""Opening hours from OpenStreetMap. Prepared by Josh Torney.

Fetches every named place in Victoria that has opening hours on OpenStreetMap (one Overpass API query),
matches each one to a venue in locations.json by name, type and distance, and stores the OSM hours
string in that venue's "oh" field. Venues OSM can't vouch for have "oh" removed, so the planner falls
back to a Google lookup for them. Free, and never touches the Google key.

Opening hours data (c) OpenStreetMap contributors, available under the Open Database Licence.

  python tools/osm_hours.py              fetch, match and update locations.json
  python tools/osm_hours.py --dry-run    report only
  python tools/osm_hours.py --dump F     also save the nearby OSM places to F (for tuning)
  python tools/osm_hours.py --from F     use a saved dump instead of fetching
"""
import argparse, datetime, json, math, pathlib, re, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOC = ROOT / 'locations.json'
STATE = ROOT / 'tools' / 'hours_state.json'
MIRRORS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.private.coffee/api/interpreter',
           'https://maps.mail.ru/osm/tools/overpass/api/interpreter']
QUERY = ('[out:json][timeout:600];area["ISO3166-2"="AU-VIC"]->.v;'
         'nwr(area.v)["opening_hours"]["name"];out center tags;')
UA = 'VN-Venue-Map weekly hours refresh (github.com/jtorney92/VN-Venue-Map)'
KEEP_TAGS = ('name', 'alt_name', 'official_name', 'old_name', 'brand', 'opening_hours', 'amenity', 'shop',
             'craft', 'tourism', 'leisure', 'club', 'sport', 'addr:housenumber', 'addr:street', 'check_date:opening_hours')


def fetch():
    body = urllib.parse.urlencode({'data': QUERY}).encode()
    last = None
    for attempt in range(2):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=body, headers={'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=660) as r:
                    j = json.load(r)
                if j.get('elements'):
                    print(f'OSM: {len(j["elements"])} places with hours from {url}')
                    return j['elements']
                last = 'empty result from ' + url
            except Exception as e:  # try the next mirror
                last = f'{url}: {e}'
                print('Overpass failed,', last, file=sys.stderr)
            time.sleep(20)
    raise SystemExit('Could not reach any Overpass server: ' + str(last))


def compact(elements):
    out = []
    for e in elements:
        lat = e.get('lat', (e.get('center') or {}).get('lat'))
        lng = e.get('lon', (e.get('center') or {}).get('lon'))
        if lat is None: continue
        t = {k: v for k, v in (e.get('tags') or {}).items() if k in KEEP_TAGS}
        out.append({'id': e['type'][0] + str(e['id']), 'lat': round(lat, 6), 'lng': round(lng, 6), 't': t})
    return out


def km(a, b, c, d):
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--dump')
    ap.add_argument('--from', dest='src')
    a = ap.parse_args()
    locs = json.loads(LOC.read_text())
    osm = json.loads(pathlib.Path(a.src).read_text()) if a.src else compact(fetch())
    if a.dump:
        cell = lambda la, ln: (int(la * 100), int(ln * 100))
        near = {(cx + dx, cy + dy) for l in locs for cx, cy in [cell(l['lat'], l['lng'])] for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        keep = [p for p in osm if cell(p['lat'], p['lng']) in near]
        pathlib.Path(a.dump).write_text(json.dumps(keep, separators=(',', ':'), ensure_ascii=False))
        print(f'Dumped {len(keep)} nearby OSM places to {a.dump}')
        if not a.src and a.dry_run: return


if __name__ == '__main__':
    main()
