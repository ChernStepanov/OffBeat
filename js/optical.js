window.OB = window.OB || {};
OB.bindOptical = function (map, select, status, mirror) {
  let site, index, overlay, mirrorOverlay, serial=0, followDate=false;
  function clear() { if (overlay) map.removeLayer(overlay); if (mirrorOverlay) mirror.removeLayer(mirrorOverlay); overlay=null; mirrorOverlay=null; }
  function draw() {
    clear();
    select.dispatchEvent(new Event('ob:select-sync'));
    const entry=index?.entries[Number(select.value)];
    if (select.value==='context' || !entry) {
      status.textContent='Esri context mosaic: dates vary, not date-matched validation.'; return;
    }
    if (entry.status!=='ready' || !entry.path || !entry.bounds) {
      status.textContent=`No dated optical image for NISAR ${entry.nisar_date}: ${entry.reason || 'no suitable observation'}. Context mosaic remains visible.`; return;
    }
    const b=entry.bounds;
    const current=L.imageOverlay(`${entry.path}?v=${entry.sha256}`,[[b.s,b.w],[b.n,b.e]],{attribution:'Copernicus Sentinel-2 / Earth Search'});
    overlay=current;
    if (mirror) mirrorOverlay=L.imageOverlay(`${entry.path}?v=${entry.sha256}`,[[b.s,b.w],[b.n,b.e]],{pane:'opticalMirror',className:'grayscale-imagery',interactive:false}).addTo(mirror);
    current.on('error',()=>{if (overlay!==current) return; clear();status.textContent='Dated optical image failed to load. Context mosaic remains visible.';});
    current.on?.('load',()=>{if (overlay===current) sharpen();});
    current.addTo(map);
    status.textContent=`${entry.source} | ${entry.date} | NISAR ${entry.nisar_date} | AOI cloud/shadow/snow ${Math.round(entry.aoi_cloud_shadow_snow_fraction*100)}% | ${entry.scene_id}`;
    select.title=status.textContent;
  }
  // Sentinel-2 is 10 m per pixel. Stretched past twice its size the browser's smoothing turns it
  // into a blur next to the sharp basemap, so from there it is drawn as the honest 10 m squares.
  function sharpen() {
    for (const img of [overlay?.getElement?.(), mirrorOverlay?.getElement?.()]) {
      if (img && img.naturalWidth) img.style.imageRendering=img.getBoundingClientRect().width/img.naturalWidth>=2 ? 'pixelated' : 'auto';
    }
  }
  map.on?.('zoomend',sharpen);
  function setDate(date) {
    if (!followDate || !index?.entries?.length) return;
    const target=Date.parse(date);
    let best=0;
    index.entries.forEach((e,i)=>{if(Math.abs(Date.parse(e.nisar_date)-target)<Math.abs(Date.parse(index.entries[best].nisar_date)-target)) best=i;});
    select.value=String(best);draw();
  }
  select.addEventListener('change',() => { followDate=select.value!=='context'; draw(); });
  return {
    setDate,
    async load(next,date) {
      site=next;index=null;followDate=false;clear();const ticket=++serial;
      select.replaceChildren(new Option('Context mosaic (date varies)','context'));
      select.disabled=true;status.textContent='Loading dated optical observations…';
      try {
        const response=await fetch(`data/${site.id}/optical/index.json`,{cache:'no-cache',signal:AbortSignal.timeout(12000)});
        if(!response.ok) throw Error('No optical index');
        const data=await response.json();if(ticket!==serial)return;
        if(data.site!==site.id || data.schema_version!==1 || !Array.isArray(data.entries)) throw Error('Invalid optical index');
        index=data;
        index.entries.forEach((entry,i)=>select.add(new Option(entry.status==='ready'
          ? `${entry.date} / radar ${entry.nisar_date}` : `No clear optical image / radar ${entry.nisar_date}`,String(i))));
        select.disabled=false;select.value='context';draw();
      } catch {if(ticket===serial)status.textContent='No prepared dated optical observations. Esri mosaic is geographic context only.';}
    },
    context() {
      serial++;index=null;followDate=false;clear();select.value='context';select.disabled=true;
      select.title='Dated Sentinel-2 images are prepared for the demo sites only';
      select.dispatchEvent(new Event('ob:select-sync'));
      status.textContent='Dated Sentinel-2 images exist for the demo sites only; here the Esri photo mosaic is shown (dates vary).';
    }
  };
};
