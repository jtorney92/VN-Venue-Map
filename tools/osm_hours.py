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


# ---------- matching ----------
# Which OSM tags fit each venue type. A venue only takes hours from an OSM place of a fitting kind, unless the
# names are identical, so a hotel's bottle shop doesn't pick up the front bar's hours.
FITS = {
    'Bottle shop': {'shop': {'alcohol', 'wine', 'beverages'}},
    'Pub / Hotel': {'amenity': {'pub', 'bar', 'restaurant', 'biergarten', 'nightclub'}, 'tourism': {'hotel', 'motel'}},
    'Bar': {'amenity': {'bar', 'pub', 'nightclub', 'restaurant', 'cafe', 'biergarten'}},
    'Restaurant / Cafe': {'amenity': {'restaurant', 'cafe', 'bar', 'pub', 'food_court', 'fast_food'}},
    'Club': {'amenity': {'social_club', 'bar', 'pub', 'restaurant', 'community_centre', 'social_facility'}, 'leisure': None, 'club': None, 'sport': None},
    'Winery / Distillery': {'craft': {'winery', 'brewery', 'distillery'}, 'tourism': {'winery'}, 'shop': {'wine', 'alcohol'},
                            'amenity': {'restaurant', 'bar', 'cafe', 'pub'}},
    'Function / Events': {'amenity': {'events_venue', 'theatre', 'arts_centre', 'community_centre', 'conference_centre', 'restaurant', 'bar', 'pub', 'cafe'},
                          'leisure': None, 'tourism': None},
    'Accommodation': {'tourism': {'hotel', 'motel', 'guest_house', 'caravan_site', 'apartment', 'chalet', 'hostel'}, 'amenity': {'restaurant', 'bar', 'pub'}},
    'Gift / Retail': {'shop': None},
}
def fits(cat, t):
    rule = FITS.get(cat)
    if rule is None: return True   # Other, Corporate: anything
    return any(k in t and (vals is None or t[k] in vals) for k, vals in rule.items())

GENERIC = {'the', 'and', 'of', 'at', 'on', 'by', 'pty', 'ltd', 'inc', 'co', 'bar', 'cafe', 'hotel', 'restaurant', 'liquor', 'liquors',
           'cellars', 'club', 'pub', 'kitchen', 'store', 'shop', 'wine', 'wines', 'bistro', 'bistrot', 'tavern', 'inn', 'house', 'eatery',
           'room', 'dining', 'grill', 'cuisine', 'espresso', 'coffee', 'cocktails', 'brewing', 'brewery', 'company', 'pizzeria', 'trattoria',
           'japanese', 'indian', 'thai', 'chinese', 'italian', 'vietnamese', 'mexican', 'greek', 'korean', 'lebanese', 'turkish', 'malaysian',
           'aust', 'australia', 'vic', 'victoria', 'melbourne', 'geelong', 'family', 'food', 'foods', 'lounge', 'e', 'en'}
# Too common to identify a business on their own
COMMON = {'royal', 'grand', 'central', 'commercial', 'railway', 'station', 'national', 'star', 'park', 'bay', 'beach', 'city', 'town',
          'golden', 'union', 'sports', 'bowls', 'golf', 'football', 'cricket', 'tennis', 'hall', 'community', 'local', 'corner', 'village',
          'garden', 'gardens', 'river', 'lake', 'hill', 'ocean', 'coast', 'street', 'road', 'new', 'old', 'little', 'big', 'top', 'best',
          'good', 'north', 'south', 'east', 'west', 'port', 'harbour', 'bridge', 'market', 'social', 'public', 'olde', 'ye', 'bros', 'pizza'}
BANNERS = re.compile(r'bottlemart|cellarbrations|thirsty camel|bottle-?o\b|liquor legends|iga liquor|local liquor|porters|duncans|independent liquor|super liquor|bottle shop', re.I)
def clean(s): return s.lower().replace('\u2019', "'").replace('&', ' and ')
def key(s): return re.sub(r'[^a-z0-9]', '', re.sub(r'^the\s+', '', clean(s)))
def tlist(s, place=()): return [t for t in re.sub(r"'s\b", '', re.sub(r'[^a-z0-9\' ]', ' ', clean(s))).replace("'", '').split()
                                 if t not in GENERIC and t not in place and len(t) > 1]
def toks(s, place=()): return set(tlist(s, place))
def name_score(a, b, place=(), d=0):
    """2 = same name, 1 = clearly the same business, 0 = can't tell"""
    ka, kb = key(a), key(b)
    if not ka or not kb: return 0
    if ka == kb: return 2
    short, long_ = sorted((ka, kb), key=len)
    if len(short) >= 6 and long_.startswith(short) and d <= 80: return 1
    ta, tb = toks(a, place), toks(b, place)
    if not ta or not tb: return 0
    if ta == tb: return 1
    # otherwise each name must lead with a word the other has ("Mitre Tavern" and "Ye Olde Mitre Tavern Hotel"),
    # so "Zinc at Federation Square" doesn't take Federation Square's hours
    lead = lambda n: next((t for t in tlist(n, place) if t not in COMMON and len(t) >= 3), None)
    if lead(a) not in tb or lead(b) not in ta: return 0
    if len(ta & tb) / len(ta | tb) >= 0.6: return 1
    small, big = sorted((ta, tb), key=len)
    if small <= big and d <= 80 and any(len(t) >= 4 and t not in COMMON for t in small): return 1
    return 0
def match(locs, osm):
    grid = {}
    for p in osm:
        grid.setdefault((int(p['lat'] * 100), int(p['lng'] * 100)), []).append(p)
    count = {}
    for l in locs: count[key(l['n'])] = count.get(key(l['n']), 0) + 1
    out = {}
    for l in locs:
        if 'Mobile bar' in (l.get('note') or ''): continue
        cx, cy = int(l['lat'] * 100), int(l['lng'] * 100)
        place = set(clean(l.get('sub') or '').split())
        chain = count.get(key(l['n']), 0) >= 3   # Dan Murphy's, Liquorland...: only the store right there
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for p in grid.get((cx + dx, cy + dy), []):
                    d = km(l['lat'], l['lng'], p['lat'], p['lng']) * 1000
                    if d > 250: continue
                    t = p['t']
                    names = [t.get(k) for k in ('name', 'alt_name', 'official_name') if t.get(k)]
                    ns = max((name_score(l['n'], n, place, d) for n in names), default=0)
                    ok = fits(l['cat'], t)
                    why = None
                    if ns == 2 and d <= (150 if chain else 250) and (ok or d <= 60): why = 'name'
                    elif ns == 1 and ok and d <= 150: why = 'similar name'
                    elif ns == 0 and l['cat'] == 'Bottle shop' and ok and d <= 20 and BANNERS.search(t.get('name', '')):
                        why = 'banner'   # an independent bottle shop trading under Bottlemart, Cellarbrations etc.
                    if not why: continue
                    rank = ({'name': 0, 'similar name': 1, 'banner': 2}[why], d)
                    if best is None or rank < best[0]: best = (rank, p, why, d)
        if best: out[l.get('vid') or l['n']] = best
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--dump')
    ap.add_argument('--from', dest='src')
    ap.add_argument('--report')
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
    found = match(locs, osm)
    n_all = sum(1 for l in locs if 'Mobile bar' not in (l.get('note') or ''))
    added = changed = removed = 0
    for l in locs:
        k = l.get('vid') or l['n']
        oh = found[k][1]['t'].get('opening_hours', '').strip() if k in found else ''
        if oh and l.get('oh') != oh:
            added += 'oh' not in l; changed += 'oh' in l; l['oh'] = oh
        elif not oh and 'oh' in l:
            del l['oh']; removed += 1
    print(f'Matched {len(found)} of {n_all} venues to OpenStreetMap places with hours '
          f'({added} new, {changed} changed, {removed} no longer on OSM)')
    if a.report:
        rows = []
        for l in locs:
            k = l.get('vid') or l['n']
            if k in found:
                rank, p, why, d = found[k]
                rows.append(f"{why:12} {d:5.0f}m  {l['cat'][:14]:14} {l['n'][:34]:34} <- {p['t'].get('name','')[:34]:34} {p['t'].get('opening_hours','')[:50]}")
        pathlib.Path(a.report).write_text('\n'.join(rows))
    if a.dry_run: return
    if added or changed or removed or not STATE.exists():   # only touch the repo when something changed
        json.dump(locs, open(LOC, 'w'), ensure_ascii=False, separators=(',', ':'))
        STATE.write_text(json.dumps({'updated': datetime.date.today().isoformat(), 'venues_with_hours': len(found),
                                     'venues': n_all, 'osm_places_in_victoria': len(osm)}, indent=1))

if __name__ == '__main__':
    main()