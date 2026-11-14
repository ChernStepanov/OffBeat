window.OB = window.OB || {};
OB.bindOptical = function (map, select, status) {
  let site, index, overlay, serial=0;
  function clear() { if (overlay) map.removeLayer(overlay); overlay=null; }
  function draw() {
    clear();
    const entry=index?.entries[Number(select.value)];
    if (select.value==='context' || !entry) {
      status.textContent='Esri context mosaic: dates vary, not date-matched validation.'; return;
    }
    if (entry.status!=='ready' || !entry.path || !entry.bounds) {
      status.textContent=`No dated optical image for NISAR ${entry.nisar_date}: ${entry.reason || entry.status}. Context mosaic remains visible.`; return;
    }
    const b=entry.bounds;
    overlay=L.imageOverlay(`${entry.path}?v=${entry.sha256}`,[[b.s,b.w],[b.n,b.e]],{attribution:'Copernicus Sentinel-2 / Earth Search'});
    overlay.on('error',()=>{clear();status.textContent='Dated optical image failed to load. Context mosaic remains visible.';});
    overlay.addTo(map);
    status.textContent=`${entry.source} | ${entry.date} | NISAR ${entry.nisar_date} | AOI cloud/shadow/snow ${Math.round(entry.aoi_cloud_shadow_snow_fraction*100)}% | ${entry.scene_id}`;
    select.title=status.textContent;
  }
  function setDate(date) {
    if (!index?.entries?.length) return;
    const target=Date.parse(date);
    let best=0;
    index.entries.forEach((e,i)=>{if(Math.abs(Date.parse(e.nisar_date)-target)<Math.abs(Date.parse(index.entries[best].nisar_date)-target)) best=i;});
    select.value=String(best);draw();
  }
  select.addEventListener('change',draw);
  return {
    setDate,
    async load(next,date) {
      site=next;index=null;clear();const ticket=++serial;
      select.replaceChildren(new Option('Context mosaic (date varies)','context'));
      select.disabled=true;status.textContent='Loading dated optical observations…';
      try {
        const response=await fetch(`data/${site.id}/optical/index.json`,{cache:'no-cache',signal:AbortSignal.timeout(12000)});
        if(!response.ok) throw Error('No optical index');
        const data=await response.json();if(ticket!==serial)return;
        if(data.site!==site.id || data.schema_version!==1 || !Array.isArray(data.entries)) throw Error('Invalid optical index');
        index=data;
        index.entries.forEach((entry,i)=>select.add(new Option(entry.status==='ready'
          ? `${entry.date} / radar ${entry.nisar_date}` : `Unavailable / radar ${entry.nisar_date}`,String(i))));
        select.disabled=false;setDate(date || site.dates.at(-1));
      } catch {if(ticket===serial)status.textContent='No prepared dated optical observations. Esri mosaic is geographic context only.';}
    },
    context() {serial++;index=null;clear();select.value='context';select.disabled=true;draw();}
  };
};
