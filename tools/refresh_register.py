#!/usr/bin/env python3
"""Monthly venue refresh from the Liquor Control Victoria licence register.

Prepared by Josh Torney.

Run by the "Monthly venue refresh" GitHub job, or by hand:
    python tools/refresh_register.py                  # finds the newest register on data.vic.gov.au
    python tools/refresh_register.py --file reg.xlsx  # uses a register file you already have
    python tools/refresh_register.py --dry-run        # reports what would change, writes nothing

What it does, matching each venue on its liquor licence number:
  * existing venues keep their name, type, priority, status and notes; address, licence type,
    capacity and position are updated from the register
  * a venue whose licence has left the register is removed if nobody has touched it
    (still Available, no notes); otherwise it stays, with a note to check it is still trading
  * new licences in Geelong, Surf Coast, Queenscliffe and Golden Plains are added, plus mobile
    bars anywhere in Victoria, with type, priority, route day and region worked out the same way
    as the rest of the list
"""
import argparse, io, json, math, os, re, sys, urllib.request
from datetime import date

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOC_FILE = os.path.join(ROOT, 'locations.json')
STATE_FILE = os.path.join(ROOT, 'tools', 'register_state.json')
LOG_FILE = os.path.join(ROOT, 'REGISTER_UPDATES.md')
API = 'https://discover.data.vic.gov.au/api/3/action/package_show?id=victorian-liquor-licences-by-location'

AREA_COUNCILS = {'GREATER GEELONG CITY COUNCIL', 'SURF COAST SHIRE COUNCIL', 'QUEENSCLIFFE BOROUGH COUNCIL', 'GOLDEN PLAINS SHIRE COUNCIL'}
KEEP = {'Restaurant and cafe Licence', 'General Licence', 'Packaged Liquor Licence', 'On-Premises Licence', 'On-premises Licence',
        "Producer's Licence", 'Full Club Licence', 'Restricted Club Licence', 'Late night (general) Licence',
        'Late night (on-premises) Licence', 'Late night (packaged liquor) Licence', 'Limited Licence'}
LIC_SHORT = {'Restaurant and cafe Licence': 'Restaurant & cafe', 'General Licence': 'General (pub)', 'Packaged Liquor Licence': 'Packaged liquor',
             'On-Premises Licence': 'On-premises', 'On-premises Licence': 'On-premises', "Producer's Licence": "Producer's",
             'Full Club Licence': 'Full club', 'Restricted Club Licence': 'Restricted club', 'Late night (general) Licence': 'Late night (general)',
             'Late night (on-premises) Licence': 'Late night (on-premises)', 'Late night (packaged liquor) Licence': 'Late night (packaged)',
             'Limited Licence': 'Limited', 'Pre-retail Licence': 'Pre-retail', "Remote Seller's Licence": 'Remote seller', 'BYO Permit': 'BYO'}

MOBILE_BAR = re.compile(r"mobile bar|mobile cocktail|mobile bartender|bar hire|bar cart|caravan bar|cocktail cart|prosecco van|tap truck|horsebox bar", re.I)
# licence holders under Limited licences that are people or businesses with nothing to sell spirits through
SKIP_NAMES = {'australian airconditioning distrubtors', 'ionization marketing agency', 'kings funeral services', 'lindros david mark', "o'brien susanne evelyn"}
SKIP_CHAINS = re.compile(r"\b(mcdonald'?s?|kfc|subway|hungry jack'?s?|domino'?s|pizza hut|red rooster|oporto|nando'?s|guzman y gomez|gyg|zambrero|mad mex|taco bell|carl'?s jr|wendy'?s|burger king|popeyes|schnitz|lord of the fries|grill'?d|betty'?s burgers|el jannah|ogalo|chicken treat|crust pizza|pizza capers|eagle boys|noodle box|roll'?d|sushi hub|sushi sushi|boost juice|starbucks|gloria jean'?s|muffin break|michel'?s|bakers delight|brumby'?s|donut king|krispy kreme|chatime|gong cha|7-eleven|woolworths|coles supermarket|aldi|costco|fish (and|&|n) chips?|fish ?n ?chips|chippy|kebab|takeaway|take away)\b", re.I)

# ---------- names, types and priorities (same rules as the rest of the list) ----------
KEEPUP = {'IGA', 'BWS', 'RSL', 'CBD', 'TAFE', 'FC', 'VR', 'BIG', 'QV', 'RACV', 'SUPA', 'ANB', 'B&B'}
def tidy(s):
    out = []
    for w in re.sub(r'\s+', ' ', str(s)).strip().split():
        if w.upper() in KEEPUP: out.append(w.upper()); continue
        out.append(re.sub(r"'S\b", "'s", w.capitalize()))
    name = ' '.join(out)
    for _ in range(2):
        name = re.sub(r'[\s,]+(pty\.?\s*ltd\.?|pty\.?\s*limited|limited|ltd\.?|inc\.?|incorporated)$', '', name, flags=re.I).strip()
    return name

FUNC = re.compile(r'reception|function|event|convention|conference|centre|center|arts|theatre|stadium|arena|university|tafe|institute|golf|bowl|racing|race|tenpin|sports|hall|pavilion|venue|gardens|estate', re.I)
BARW = re.compile(r'\bbar\b|lounge|pub\b|tavern|brewhouse|taphouse|bierhaus|cocktail|speakeasy|wine bar|whisk', re.I)
FOOD = re.compile(r'restaurant|kitchen|cafe|café|bistro|trattoria|pizz|grill|eatery|dining|diner|thai|indian|sushi|izakaya|cucina|osteria|taverna', re.I)
ACCOM = re.compile(r'motel|motor inn|\binn\b|holiday park|holidays|suites|resort|guest ?house|cottage|retreat|b ?& ?b|bed and breakfast|lodge|caravan park|bnb|villa\b|chalet|farmstay|apartments', re.I)
GIFT = re.compile(r'flor|flower|bridal|gift|hamper|provedore|general store|\bstore\b|nursery|chocolate|salon|gallery|pantry|wholefoods|produce|platter|olive oil|art studio|boutique|deli\b|foods\b', re.I)
EVENT = re.compile(r'cater|event|wedding|mobile bar|caravan bar|keg|charter|cruise|tour|reception|pavilion|pavillion|hall|centre|palais|warehouse|experience|botanic', re.I)
CLUB = re.compile(r'club|rsl|association|league|united|\bfc\b|sporting|soccer|cricket|football|netball|bowls|golf|baseball|rugby|hockey|softball|tennis|surf life|angling|yacht|social group', re.I)
BREW = re.compile(r'\bbar\b|brew|beverage', re.I)
WINE = re.compile(r'wine|vineyard|estate|winery', re.I)

def category(lic, name, cap):
    if MOBILE_BAR.search(name): return 'Function / Events'
    l = lic.lower()
    if 'limited' in l:
        for cat, pat in [('Accommodation', ACCOM), ('Gift / Retail', GIFT), ('Club', CLUB), ('Function / Events', EVENT),
                         ('Bar', BREW), ('Winery / Distillery', WINE), ('Restaurant / Cafe', FOOD)]:
            if pat.search(name): return cat
        return 'Other'
    if ACCOM.search(name) and 'packaged' not in l: return 'Accommodation'
    if 'packaged' in l: return 'Bottle shop'
    if 'general' in l: return 'Pub / Hotel'
    if 'club' in l: return 'Club'
    if 'producer' in l: return 'Winery / Distillery'
    if 'restaurant' in l: return 'Restaurant / Cafe'
    if BARW.search(name): return 'Bar'
    if FUNC.search(name) or (cap and cap >= 300 and not FOOD.search(name)): return 'Function / Events'
    if FOOD.search(name): return 'Restaurant / Cafe'
    return 'Bar'

CHAIN_BOTTLE = re.compile(r"dan murphy|\bbws\b|beer wine spirits|liquorland|first choice|vintage cellars|aldi|liquor ?land", re.I)
NOT_PROSPECT = re.compile(r"cinema|university|college|\btafe\b|centre for tourism|ferr(y|ies)|geelong flyer|searoad|transport|adventure park|retirement village|church|seafarers", re.I)
def priority(v):
    cat, cap, lic = v['cat'], v.get('cap') or 0, v.get('lic', '')
    if MOBILE_BAR.search(v['n']): return 'A'
    if cat in ('Function / Events', 'Other') and NOT_PROSPECT.search(v['n']): return 'C'
    if cat == 'Bottle shop':
        if CHAIN_BOTTLE.search(v['n']): return 'C'
        if re.search(r'IGA|Foodworks|Supermarket|Grocer', v['n'], re.I): return 'B'
        return 'A'
    if cat == 'Bar': return 'A'
    if cat == 'Function / Events': return 'A' if cap >= 150 else 'B'
    if cat == 'Pub / Hotel': return 'B'
    if cat == 'Restaurant / Cafe': return 'B' if re.search(r'General|On-premises|Late night', lic) or cap >= 80 else 'C'
    if cat in ('Gift / Retail', 'Accommodation', 'Corporate / Gifting', 'Club'): return 'B'
    return 'C'

# same venue, different licence or spelling: same name start, or most of the name's words in common
STOP = {'the', 'and', 'of', 'at', 'on', 'pty', 'ltd', 'bar', 'cafe', 'hotel', 'restaurant', 'liquor', 'cellars', 'by', '&', 'inc', 'club'}
def toks(s): return {t for t in re.sub(r'[^a-z0-9 ]', ' ', s.lower()).split() if t not in STOP and len(t) > 1}
def same(a, b):
    ka, kb = re.sub(r'[^a-z0-9]', '', a.lower().removeprefix('the ')), re.sub(r'[^a-z0-9]', '', b.lower().removeprefix('the '))
    if ka[:10] == kb[:10] and len(ka) >= 5: return True
    ta, tb = toks(a), toks(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.6

# ---------- region, route day and suburb ----------
def km(a, b, c, d):
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2))
G, M = (-38.1499, 144.3617), (-37.8136, 144.9631)
ZONES = [('Mon - Geelong CBD & West', -38.143, 144.355),
         ('Tue - Surf Coast', -38.360, 144.240), ('Tue - Surf Coast', -38.540, 143.975),
         ('Wed - Bellarine', -38.230, 144.600), ('Wed - Bellarine', -38.170, 144.560),
         ('Thu - Highton, Belmont & South', -38.183, 144.335), ('Thu - Highton, Belmont & South', -38.212, 144.295), ('Thu - Highton, Belmont & South', -38.232, 144.370),
         ('Fri - North & Golden Plains', -38.060, 144.390), ('Fri - North & Golden Plains', -37.980, 144.180)]
SURF = {'Torquay', 'Jan Juc', 'Bellbrae', 'Anglesea', 'Aireys Inlet', 'Fairhaven', 'Lorne', 'Wye River', 'Kennett River', 'Apollo Bay', 'Moriac', 'Winchelsea',
        'Deans Marsh', 'Freshwater Creek', 'Bells Beach', 'Breamlea', 'Eastern View', 'Separation Creek', 'Skenes Creek', 'Mount Duneed'}
BELL = {'Leopold', 'Ocean Grove', 'Barwon Heads', 'Queenscliff', 'Point Lonsdale', 'Drysdale', 'Clifton Springs', 'Portarlington', 'St Leonards', 'Indented Head',
        'Curlewis', 'Wallington', 'Mannerim', 'Marcus Hill', 'Swan Bay', 'Connewarre', 'Bellarine'}
SUB_FIX = {'Queenscliffe': 'Queenscliff', 'Geelong East': 'East Geelong', 'Geelong South': 'South Geelong', 'Geelong North': 'North Geelong', 'Conawarre': 'Connewarre'}
def suburb(a):
    m = re.search(r',\s*([A-Za-z][A-Za-z\' .-]+?)\s*,?\s*(?:VIC|Victoria)\b', a or '', re.I)
    s = m.group(1).strip().title() if m else ''
    return SUB_FIX.get(s, s)
def region(v):
    p = (v['lat'], v['lng'])
    if p[1] >= 144.69 and p[0] < -38.2: return 'Melbourne'   # Mornington Peninsula: across the bay
    if v['sub'] in SURF | BELL: return 'Geelong & surrounds'
    dg, dm = km(G[0], G[1], *p), km(M[0], M[1], *p)
    if dg <= 45 and dg < dm: return 'Geelong & surrounds'
    if dm <= 40: return 'Melbourne'
    return 'Regional VIC'
def zone(v):
    if v['sub'] in SURF: return 'Tue - Surf Coast'
    if v['sub'] in BELL: return 'Wed - Bellarine'
    if v['region'] != 'Geelong & surrounds':
        return 'Monthly - Ballarat & Daylesford' if min(km(-37.56, 143.85, v['lat'], v['lng']), km(-37.35, 144.14, v['lat'], v['lng'])) <= 40 else ''
    return min(ZONES, key=lambda z: km(z[1], z[2], v['lat'], v['lng']))[0]

# ---------- the register ----------
def latest_register():
    with urllib.request.urlopen(API, timeout=60) as r:
        pkg = json.load(r)['result']
    files = [x for x in pkg['resources'] if (x.get('format') or '').lower() in ('xlsx', 'xls') or x.get('url', '').lower().endswith('.xlsx')]
    files.sort(key=lambda x: x.get('last_modified') or x.get('created') or '', reverse=True)
    if not files: sys.exit('No register file found on data.vic.gov.au')
    return files[0]['url']

def read_register(src):
    raw = pd.read_excel(src, header=None, dtype=str)
    hdr = next(i for i, row in raw.iterrows() if str(row.iloc[0]).strip() == 'Licence Number')
    df = raw.iloc[hdr + 1:].copy(); df.columns = [str(c).strip() for c in raw.iloc[hdr]]
    df = df[df['Licence Number'].notna()]
    df['Licence Number'] = df['Licence Number'].astype(str).str.strip()
    for c in ('Latitude', 'Longitude'): df[c] = pd.to_numeric(df[c], errors='coerce')
    df['cap'] = pd.to_numeric(df['Patron Capacity (if applicable)'], errors='coerce')
    title = next((str(v) for v in raw.iloc[:hdr, 0] if isinstance(v, str) and 'as of' in v.lower()), '')
    asof = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', title)
    return df, asof.group(1) if asof else ''

def address(r):
    if not isinstance(r['Street Address'], str) or 'not applicable' in r['Street Address'].lower(): return ''
    pc = r['Postcode']
    pc = str(int(float(pc))) if isinstance(pc, str) and pc.strip().replace('.0', '').isdigit() else ''
    return ', '.join(x for x in [tidy(r['Street Address']), tidy(r['Suburb']) if isinstance(r['Suburb'], str) else '', ('VIC ' + pc) if pc else ''] if x)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file'); ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    src = args.file or latest_register()
    regname = os.path.basename(src.split('?')[0])
    if not args.force and not args.file and state.get('last_file') == regname:
        print('No new register since', regname); return
    if src.startswith('http'):
        with urllib.request.urlopen(src, timeout=120) as r: src = io.BytesIO(r.read())
    reg, asof = read_register(src)
    month = pd.to_datetime(asof, dayfirst=True).strftime('%B %Y') if asof else date.today().strftime('%B %Y')
    by_lno = {r['Licence Number']: r for _, r in reg.iterrows()}

    locs = json.load(open(LOC_FILE))
    updated, removed, flagged, added = 0, [], [], []
    keep = []
    for v in locs:
        lno = str(v.get('lno') or '').split('-')[0]
        if not lno or v.get('src') == 'manual':
            keep.append(v); continue
        r = by_lno.get(lno)
        if r is None:
            if v.get('st', 'available') == 'available' and not v.get('note'):
                removed.append(v); continue
            msg = f'Not on the register as of {month}: check it is still trading'
            if msg not in v.get('note', ''):
                v['note'] = (v['note'] + ' | ' if v.get('note') else '') + msg; flagged.append(v)
            keep.append(v); continue
        before = (v.get('a'), v.get('cap'), v.get('lat'), v.get('lng'))
        if not pd.isna(r['cap']) and v.get('cap') != int(r['cap']): v['cap'] = int(r['cap'])
        # address and pin only change together, when the register shows the venue has moved (more than 150 m)
        a = address(r)
        if a and not pd.isna(r['Latitude']) and km(v['lat'], v['lng'], r['Latitude'], r['Longitude']) > 0.15:
            v['lat'], v['lng'], v['a'] = round(float(r['Latitude']), 5), round(float(r['Longitude']), 5), a
            v['sub'] = suburb(a); v['region'] = region(v); v['zone'] = zone(v)
        if (v.get('a'), v.get('cap'), v.get('lat'), v.get('lng')) != before: updated += 1
        keep.append(v)
    locs = keep

    have = {str(v.get('lno') or '').split('-')[0] for v in locs}
    names = {re.sub(r'[^a-z0-9]', '', v['n'].lower()) for v in locs}
    near = {}
    for i, v in enumerate(locs): near.setdefault((round(v['lat'] * 200), round(v['lng'] * 200)), []).append(i)
    for lno, r in by_lno.items():
        if lno in have or pd.isna(r['Latitude']): continue
        raw_name = r['Trading As'] if isinstance(r['Trading As'], str) and r['Trading As'].strip() else r['Licensee']
        name = tidy(raw_name)
        mobile = bool(MOBILE_BAR.search(name))
        if not mobile and (r['Council'] not in AREA_COUNCILS or r['Licence Category'] not in KEEP): continue
        if SKIP_CHAINS.search(name) or name.lower() in SKIP_NAMES or str(raw_name).strip().lower() in SKIP_NAMES: continue
        if mobile and re.sub(r'[^a-z0-9]', '', name.lower()) in names: continue   # a second licence for a mobile bar already listed
        a = address(r)
        if not a: continue
        lat, lng = round(float(r['Latitude']), 5), round(float(r['Longitude']), 5)
        # a second licence for a venue already on the map: same name within 200 m
        cell = (round(lat * 200), round(lng * 200))
        twin = next((locs[i] for dx in (-1, 0, 1) for dy in (-1, 0, 1) for i in near.get((cell[0] + dx, cell[1] + dy), [])
                     if km(lat, lng, locs[i]['lat'], locs[i]['lng']) <= 0.2 and same(name, locs[i]['n'])), None)
        if twin is not None: continue
        cap = None if pd.isna(r['cap']) else int(r['cap'])
        v = {'n': name, 'a': a, 'lat': lat, 'lng': lng, 'cat': category(r['Licence Category'], name, cap), 'st': 'available', 'src': 'lcv',
             'lic': LIC_SHORT.get(r['Licence Category'], r['Licence Category']), 'lno': lno, 'vid': lno}
        if cap: v['cap'] = cap
        v['sub'] = suburb(a); v['region'] = region(v); v['zone'] = zone(v); v['tier'] = priority(v)
        v['note'] = ('Mobile bar: weddings and events | ' if mobile else '') + f'New on the register, {month}'
        locs.append(v); added.append(v); near.setdefault(cell, []).append(len(locs) - 1); names.add(re.sub(r'[^a-z0-9]', '', name.lower()))

    locs.sort(key=lambda x: x['n'].lower())
    print(f'{regname} ({month}): {len(added)} added, {len(removed)} removed, {len(flagged)} flagged, {updated} moved or capacity updated, {len(locs)} venues')
    for v in added: print('  + ', v['n'], '|', v['sub'], '|', v['cat'], v['tier'])
    for v in removed: print('  - ', v['n'], '|', v.get('sub', ''))
    for v in flagged: print('  ? ', v['n'], '|', v.get('sub', ''))
    if args.dry_run: return

    json.dump(locs, open(LOC_FILE, 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump({'last_file': regname, 'as_of': asof, 'processed': date.today().isoformat()}, open(STATE_FILE, 'w'), indent=1)
    lines = [f'## {month} register ({date.today().isoformat()})', '',
             f'{len(added)} new venues, {len(removed)} removed (licence gone, never worked), {len(flagged)} flagged to check, {updated} moved or capacity updates.', '']
    if added: lines += ['New:'] + [f"- {v['n']}, {v['sub']} ({v['cat']}, priority {v['tier']})" for v in added] + ['']
    if removed: lines += ['Removed:'] + [f"- {v['n']}, {v.get('sub', '')}" for v in removed] + ['']
    if flagged: lines += ['Check these, they have your notes or a status but their licence has gone:'] + [f"- {v['n']}, {v.get('sub', '')}" for v in flagged] + ['']
    old = open(LOG_FILE).read() if os.path.exists(LOG_FILE) else '# Register updates\n\nPrepared by Josh Torney. Written by the monthly venue refresh.\n\n'
    head, _, rest = old.partition('\n## ')
    open(LOG_FILE, 'w').write(head.rstrip() + '\n\n' + '\n'.join(lines) + ('\n## ' + rest if rest else ''))

if __name__ == '__main__':
    main()
