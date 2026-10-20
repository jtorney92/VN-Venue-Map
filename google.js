// Google Places guard. Prepared by Josh Torney.
//
// Only the map's Find venues button uses Google, and only once a key has been pasted on this device. The key
// is never in the code: it's kept in this browser only. Every call goes through GG.call(), which counts it
// and refuses once a daily or monthly limit is reached, so a bug can never run up a bill.
//
// Find venues uses Text Search Enterprise (phone and website included): 1,000 free a month per billing
// account (March 2025 pricing). The limit below is per device, so a phone and a PC together stay under it.
const GG = (() => {
  const LIMITS = {
    find: { day: 90, month: 300, label: 'Find venues searches' },
  };
  const KEY = 'vn_gkey', USE = 'vn_gusage';
  const rd = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } };
  const wr = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } };
  const pad = n => String(n).padStart(2, '0');
  const stamp = () => { const d = new Date(); return [d.getFullYear() + '-' + pad(d.getMonth() + 1), d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())]; };

  function usage() {
    const [m, d] = stamp(), u = rd(USE, {});
    const out = {};
    for (const k in LIMITS) {
      const x = u[k] || {};
      out[k] = { month: x.m === m ? x.month || 0 : 0, day: x.d === d ? x.day || 0 : 0, m, d };
    }
    return out;
  }
  function left(kind) { const u = usage()[kind], L = LIMITS[kind]; return Math.max(0, Math.min(L.day - u.day, L.month - u.month)); }
  function key() { return (rd(KEY, '') || '').trim(); }
  function setKey(k) {
    k = (k || '').trim();
    if (k && !/^AIza[0-9A-Za-z_\-]{30,}$/.test(k)) return 'That doesn\'t look like a Google API key (they start with AIza).';
    if (!k) { try { localStorage.removeItem(KEY); } catch (e) {} return ''; }
    return wr(KEY, k) ? '' : 'This browser won\'t save it (private window?).';
  }
  function err(code, msg) { const e = new Error(msg); e.code = code; return e; }

  // Count first, then call: if the page dies mid-call the call is still counted.
  async function call(kind, url, opts) {
    const L = LIMITS[kind]; if (!L) throw err('kind', 'Unknown Google call type');
    const k = key(); if (!k) throw err('nokey', 'Add your Google key first (Settings).');
    const u = usage()[kind];
    if (u.day >= L.day) throw err('cap', `${L.label}: today's limit of ${L.day} on this device is used. It resets tomorrow.`);
    if (u.month >= L.month) throw err('cap', `${L.label}: this month's limit of ${L.month} on this device is used. It resets on the 1st.`);
    const all = rd(USE, {});
    all[kind] = { m: u.m, month: u.month + 1, d: u.d, day: u.day + 1 };
    if (!wr(USE, all)) throw err('store', 'Can\'t record the call in this browser, so it wasn\'t made.');
    const o = opts || {};
    return fetch(url, { ...o, headers: { ...(o.headers || {}), 'X-Goog-Api-Key': k } });
  }

  function summaryHtml() {
    const u = usage();
    return Object.keys(LIMITS).map(k => `${LIMITS[k].label}: ${u[k].month} of ${LIMITS[k].month} this month, ${u[k].day} of ${LIMITS[k].day} today`).join('<br>');
  }
  return { LIMITS, call, usage, left, key, setKey, summaryHtml };
})();
