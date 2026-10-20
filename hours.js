// Opening hours. Prepared by Josh Torney.
// Reads OpenStreetMap opening_hours strings (e.g. "Mo-Th 12:00-22:00; Fr,Sa 12:00-24:00; Su off") and Google's
// opening periods into one shape: a week, Monday first, each day a list of [open, close] in minutes from
// midnight. A close past midnight runs over 1440 (1am = 1500). Public holiday and seasonal rules are ignored.
const HOURS = (() => {
  const DN = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
  const SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const DAYRE = '(?:Mo|Tu|We|Th|Fr|Sa|Su)';
  const SEL = new RegExp('^(' + DAYRE + '(?:\\s*-\\s*' + DAYRE + ')?(?:\\s*,\\s*' + DAYRE + '(?:\\s*-\\s*' + DAYRE + ')?)*)(?:\\s*\\[[^\\]]*\\])?\\s*:?\\s*(.*)$');
  const MONTH = /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4}|week)\b/i;

  function days(sel) {
    const out = new Set();
    sel.split(',').forEach(part => {
      const [a, b] = part.split('-').map(s => DN.indexOf(s.trim()));
      if (a < 0) return;
      if (b == null || b < 0) { out.add(a); return; }
      for (let i = a; ; i = (i + 1) % 7) { out.add(i); if (i === b) break; }
    });
    return [...out];
  }
  const LATE = 1441;   // "12:00+": open from noon, closing time not given (shown as "till late")
  function times(t) {
    t = t.trim().replace(/\s+/g, '');
    if (/^(off|closed)$/i.test(t)) return [];
    const out = [];
    for (const span of t.split(',')) {
      let m = span.match(/^(\d{1,2}):(\d{2})\+$/);
      if (m) { out.push([+m[1] * 60 + +m[2], LATE]); continue; }
      m = span.match(/^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\+?$/);
      if (!m) return null;
      const o = +m[1] * 60 + +m[2]; let c = +m[3] * 60 + +m[4];
      if (c <= o) c += 1440;
      out.push([o, c]);
    }
    return out;
  }
  // OSM opening_hours string -> week, or null when it can't be read. A day OSM marks only with a note
  // ("Su \"ring first\"") comes back as null inside the week: unknown, not closed.
  function parseOsm(s) {
    if (!s) return null;
    s = String(s).trim();
    if (s === '24/7') return Array.from({ length: 7 }, () => [[0, 1440]]);
    const week = Array.from({ length: 7 }, () => undefined);
    let any = false;
    for (const rule of s.split(';')) {
      // ", Sa 10:00-14:00" inside a rule adds another rule rather than replacing
      const parts = rule.split(new RegExp('(?<=[\\d+"])\\s*,\\s*(?=' + DAYRE + '(?:\\s*[-,]\\s*' + DAYRE + ')*(?:\\s|$|"))'));
      for (let i = 0; i < parts.length; i++) {
        let r = parts[i].trim();
        const noted = /"[^"]*"/.test(r);
        r = r.replace(/"[^"]*"/g, '').trim();
        if (!r) continue;
        if (/^(PH|SH)\b/.test(r) || MONTH.test(r) || /^easter/i.test(r)) continue;   // holidays and seasons: skip
        r = r.replace(/^(.*?)\s*,\s*PH\b/, '$1').replace(/\bPH\s*,\s*/, '');           // "Mo-Fr,PH 10:00-18:00"
        let ds = [0, 1, 2, 3, 4, 5, 6], rest = r;
        const m = r.match(SEL);
        if (m) { ds = days(m[1]); rest = m[2]; }
        if (rest === '' && m) {
          if (noted) { ds.forEach(d => { week[d] = null; }); any = true; continue; }
          rest = '00:00-24:00';
        }
        const t = times(rest);
        if (t === null) return null;
        ds.forEach(d => { week[d] = i > 0 && Array.isArray(week[d]) ? week[d].concat(t).sort((x, y) => x[0] - y[0]) : t; });
        any = true;
      }
    }
    if (!any) return null;
    return week.map(d => d === undefined ? [] : d);   // days no rule mentions are closed
  }
  // Google regularOpeningHours.periods -> week (Google days: 0 = Sunday)
  function fromGoogle(periods) {
    if (!Array.isArray(periods) || !periods.length) return null;
    const week = Array.from({ length: 7 }, () => []);
    for (const p of periods) {
      if (!p.open) continue;
      const od = (p.open.day + 6) % 7, o = (p.open.hour || 0) * 60 + (p.open.minute || 0);
      if (!p.close) return Array.from({ length: 7 }, () => [[0, 1440]]);   // open 24 hours
      let c = (p.close.hour || 0) * 60 + (p.close.minute || 0) + 1440 * (((p.close.day - p.open.day) + 7) % 7);
      if (c <= o) c += 1440 * 7;
      week[od].push([o, c]);
    }
    week.forEach(d => d.sort((a, b) => a[0] - b[0]));
    return week;
  }
  const wdOf = date => (date.getDay() + 6) % 7;
  function fmt(n) {
    n = ((n % 1440) + 1440) % 1440;
    if (n === 0) return 'midnight';
    if (n === 720) return 'noon';
    const h = Math.floor(n / 60), m = n % 60, ap = h < 12 ? 'am' : 'pm', h12 = h % 12 || 12;
    return h12 + (m ? ':' + String(m).padStart(2, '0') : '') + ap;
  }
  const span = ([o, c]) => c === LATE ? fmt(o) + ' till late' : (o === 0 && c >= 1440) ? 'all day' : fmt(o) + '-' + fmt(c);
  function dayText(week, wd) { const d = week[wd]; return d === null ? 'not listed' : d.length ? d.map(span).join(', ') : 'closed'; }
  // intervals that cover a given day, including a late close spilling over from the night before
  function cover(week, wd) {
    const prev = (week[(wd + 6) % 7] || []).filter(([, c]) => c > 1440 && c !== LATE).map(([, c]) => [0, c - 1440]);
    return [...prev, ...(week[wd] || [])];
  }
  // state at a minute of a weekday: { open, until, late, opens, closedAllDay } or { unknown: true }
  function at(week, wd, min) {
    if (week[wd] === null) return { unknown: true };
    const iv = cover(week, wd);
    const now = iv.find(([o, c]) => o <= min && min < c);
    if (now) return { open: true, until: now[1], late: now[1] === LATE };
    const later = iv.filter(([o]) => o > min).sort((a, b) => a[0] - b[0])[0];
    return { open: false, opens: later ? later[0] : null, closedAllDay: !week[wd].length };
  }
  // "Mon closed · Tue-Thu 4pm-11pm · Fri-Sat noon-1am"
  function weekText(week) {
    const out = [];
    for (let i = 0; i < 7;) {
      const t = dayText(week, i); let j = i;
      while (j + 1 < 7 && dayText(week, j + 1) === t) j++;
      out.push((i === j ? SHORT[i] : SHORT[i] + '-' + SHORT[j]) + ' ' + t);
      i = j + 1;
    }
    return out.length === 1 && /^Mon-Sun /.test(out[0]) ? 'Every day ' + out[0].slice(8) : out.join(' · ');
  }
  return { parseOsm, fromGoogle, at, dayText, weekText, fmt, wdOf, SHORT, LATE };
})();
