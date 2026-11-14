window.OB = window.OB || {};

OB.bindArchive = function (getCenter) {
  const base = 'https://cmr.earthdata.nasa.gov';
  const search = document.getElementById('archive-search');
  const more = document.getElementById('archive-more');
  const results = document.getElementById('archive-results');
  const status = document.getElementById('archive-status');
  let collections, query, cursor, point;
  const seen = new Set();

  async function request(path, params, headers) {
    const response = await fetch(`${base}/search/${path}.json?${params}`, {
      headers,
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok || response.headers.get('CMR-Timed-Out') === 'true') {
      throw new Error('CMR search failed');
    }
    const { feed } = await response.json();
    return { entries: feed.entry, headers: response.headers };
  }

  function link(text, href) {
    const anchor = document.createElement('a');
    anchor.textContent = text;
    anchor.href = href;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    return anchor;
  }

  async function loadPage(reset) {
    search.disabled = more.disabled = true;
    status.textContent = 'Searching NASA Earthdata…';
    try {
      if (reset) {
        cursor = null;
        seen.clear();
        results.replaceChildren();
        results.hidden = more.hidden = true;
        point = getCenter();
        if (!collections) {
          const { entries } = await request('collections', new URLSearchParams({
            provider: 'ASF',
            short_name: 'NISAR_*',
            'options[short_name][pattern]': 'true',
            page_size: '2000',
          }));
          if (!entries.length) throw new Error('No NISAR collections returned');
          collections = new Map(entries.map(entry => [entry.id, entry.short_name]));
        }
        query = new URLSearchParams({
          point: `${point.lng},${point.lat}`,
          page_size: '25',
          'sort_key[]': '-start_date',
        });
        for (const id of collections.keys()) query.append('collection_concept_id[]', id);
      }
      const { entries, headers } = await request('granules', query, cursor ? { 'CMR-Search-After': cursor } : {});
      for (const entry of entries) {
        if (seen.has(entry.id)) continue;
        seen.add(entry.id);
        const item = document.createElement('li');
        const date = entry.time_start?.slice(0, 10) || 'Date unavailable';
        item.append(`${date} | ${collections.get(entry.collection_concept_id)} | `);
        item.append(link(entry.producer_granule_id || entry.title, `${base}/search/concepts/${encodeURIComponent(entry.id)}.html`));
        const file = entry.links?.find(({ inherited, rel, href }) =>
          !inherited && rel?.endsWith('/data#') && href?.startsWith('https://'));
        if (file) item.append(' | ', link('Download source', file.href));
        results.append(item);
      }
      const hits = Number(headers.get('CMR-Hits') ?? seen.size);
      cursor = headers.get('CMR-Search-After');
      results.hidden = seen.size === 0;
      more.hidden = !cursor || entries.length === 0 || seen.size >= hits;
      const coordinates = `${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`;
      status.textContent = hits
        ? `${coordinates} | Showing ${seen.size} of ${hits} ASF records. Downloads may require Earthdata Login.`
        : `${coordinates} | No ASF NISAR records found.`;
    } catch {
      status.textContent = reset
        ? 'NASA Earthdata search failed. Try searching again.'
        : 'Could not load more records. Try again.';
    } finally {
      search.disabled = more.disabled = false;
    }
  }

  search.addEventListener('click', () => loadPage(true));
  more.addEventListener('click', () => loadPage(false));
  search.disabled = false;
};
