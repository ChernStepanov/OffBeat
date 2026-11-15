// Shared moderation state. Only verdict/basis and an anonymous browser token leave the browser.
window.OB = window.OB || {};
OB.reviews = (() => {
  const base = location.hostname === 'offbeat.chern.su'
    ? 'https://offbeat-shared-reviews.glazedbream.chatgpt.site/api/v1' : '/api/v1';
  let items = new Map(), pending, loaded = 0, memoryToken;
  const key = p => `${p.site}/${p.marker}/${p.dataset}`;
  const status = counts => counts.no_visible_change > 0 ? 'rejected' : counts.visible_change > 0 ? 'visible' : 'pending';
  function token() {
    let value = memoryToken;
    try { value = localStorage.getItem('offbeat.review-token.v1') || value; } catch (_) {}
    if (!/^[a-f0-9]{64}$/.test(value || '')) value = [...crypto.getRandomValues(new Uint8Array(32))].map(x => x.toString(16).padStart(2,'0')).join('');
    memoryToken = value;
    try { localStorage.setItem('offbeat.review-token.v1', value); } catch (_) {}
    return value;
  }
  function local(p) {
    try { return JSON.parse(localStorage.getItem('offbeat.review-choice.v1.' + key(p))) || null; } catch (_) { return null; }
  }
  function own(p) { return local(p)?.verdict; }
  function update(p, result) {
    items.set(key(p), {...items.get(key(p)), ...p, counts:result.counts, status:result.status || status(result.counts)});
    document.dispatchEvent(new Event('ob:reviews-change'));
  }
  async function refresh(force = false) {
    if (!force && Date.now() - loaded < 10000) return;
    if (pending) return pending;
    pending = (async () => {
      const r = await fetch(base + '/review-queue', {cache:'no-store'});
      if (!r.ok) throw Error('Review queue unavailable');
      const data = await r.json(); if (!Array.isArray(data.items)) throw Error('Invalid review queue');
      items = new Map(data.items.map(item => [key(item), item])); loaded = Date.now();
      document.dispatchEvent(new Event('ob:reviews-change'));
    })();
    try { await pending; } finally { pending = null; }
  }
  async function get(p) {
    const r = await fetch(base + '/reviews?' + new URLSearchParams(p), {cache:'no-store'});
    if (!r.ok) throw Error('Reviews unavailable');
    const result = await r.json(); update(p,result); return result;
  }
  async function save(p, verdict, basis) {
    const r = await fetch(base + '/reviews', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...p,token:token(),verdict,basis})});
    if (!r.ok) throw Error('Could not save review');
    const result = await r.json();
    try { const storageKey='offbeat.review-choice.v1.' + key(p); if (verdict==='clear') localStorage.removeItem(storageKey); else localStorage.setItem(storageKey,JSON.stringify({verdict,basis})); } catch (_) {}
    update(p,result); try { await refresh(true); } catch (_) {} return result;
  }
  const entry = p => items.get(key(p));
  const available = p => entry(p)?.status !== 'rejected' && !['visible_change','uncertain','no_visible_change'].includes(own(p));
  // Poll only visible pages; queue requests are shared by all callers in this tab.
  setInterval(() => { if (!document.hidden) refresh(true).catch(() => {}); }, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true).catch(() => {}); });
  return {refresh, get, save, entry, own, available, all: () => [...items.values()]};
})();
