window.OB = window.OB || {};
OB.bindOptical = function (map, select, status, mirror) {
  let site, index, overlay, mirrorOverlay, serial=0, followDate=false, observationStatus='';
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
    current.on?.('load',()=>{if (overlay===current) updateDetail();});
    current.addTo(map);
    observationStatus=`${entry.source} | ${entry.date} | NISAR ${entry.nisar_date} | AOI cloud/shadow/snow ${Math.round(entry.aoi_cloud_shadow_snow_fraction*100)}% | ${entry.scene_id}`;
    status.textContent=observationStatus;
    select.title=status.textContent;
  }
  // The dated image has finite resolution. At high magnification reveal the context
  // imagery instead of covering it with enlarged blocks; restore it on zooming out.
  function updateDetail() {
    const img=overlay?.getElement?.();
    if (!img || !img.naturalWidth) return;
    const show=img.getBoundingClientRect().width/img.naturalWidth < 2;
    overlay.setOpacity(show ? 1 : 0);
    mirrorOverlay?.setOpacity(show ? 1 : 0);
    status.textContent=show ? observationStatus : observationStatus + ' | Zoomed in: showing Esri context; zoom out to see the dated image.';
  }
  map.on?.('zoomend',updateDetail);
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
