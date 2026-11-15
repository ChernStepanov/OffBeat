"""Build dated, georeferenced optical contact sheets for sampled Amazon SAR candidates."""
import hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/investigation'
DATES = ['2026-07-18','2026-08-11','2026-08-23','2026-09-04','2026-09-16','2026-09-28']

def main():
    meta=json.loads((ROOT/'data/amazon/dense-peer-z.json').read_text()); g=meta['grid']
    arrays=[np.load(ROOT/f'data/subsets/amazon-dense/{d}.npz') for d in DATES]
    hv=np.stack([a['hv'] for a in arrays]); hh=np.stack([a['hh'] for a in arrays]); masks=np.stack([a['mask'] for a in arrays])
    valid=(masks>0)&(masks<255)&np.isfinite(hv)&(hv>0)
    db=np.full(hv.shape,np.nan); db[valid]=10*np.log10(hv[valid])
    hh_valid=(masks>0)&(masks<255)&np.isfinite(hh)&(hh>0)
    hh_db=np.full(hh.shape,np.nan); hh_db[hh_valid]=10*np.log10(hh[hh_valid])
    # Same fixed 3-before/3-after screen as archived validation, evaluated per native cell.
    eligible=valid.all(0); change=np.median(db[3:],axis=0)-np.median(db[:3],axis=0)
    persistence=(db[3:]<=np.median(db[:3],axis=0)-3).sum(0)>=2
    flags=eligible & (change<=-3) & persistence
    rr,cc=np.where(flags); order=sorted(zip(rr,cc),key=lambda rc:(change[rc],rc))
    # Spatially thin candidates (>= 1 km between selected native-cell centers), then controls
    # from valid forest-context cells with smallest absolute shift, spread by same rule.
    def thin(items, limit=4):
        out=[]
        for r,c in items:
            if all((r-a)**2+(c-b)**2>=2500 for a,b in out): out.append((int(r),int(c)))
            if len(out)>=limit: break
        return out
    candidates=thin(order)
    cover=np.load(ROOT/'data/subsets/amazon-dense/worldcover-2021.npz')['cover']
    hhv=hh_valid.all(0); joint_flags=None
    hh_change=np.median(hh_db[3:],axis=0)-np.median(hh_db[:3],axis=0)
    hh_persistence=(hh_db[3:]<=np.median(hh_db[:3],axis=0)-3).sum(0)>=2
    hv_persistence=(db[3:]<=np.median(db[:3],axis=0)-3).sum(0)>=2
    joint_flags=eligible & hhv & (change<=-3) & hh_persistence & (hh_change<=-3) & hv_persistence
    possible=list(zip(*np.where(eligible & (cover==10) & ~flags)))
    controls=thin(sorted(possible,key=lambda rc:(abs(change[rc]),rc)))
    # transform native cell centers; grid arrays use EPSG:32722 coordinates.
    to_geo=Transformer.from_crs(g['epsg'],4326,always_xy=True).transform
    optical=json.loads((ROOT/'data/amazon/optical/index.json').read_text())
    entries=[e for e in optical['entries'] if e.get('status')=='ready']
    # Before / near-post / subsequent dated scenes only; never use undated basemaps.
    picks=[entries[i] for i in (0,2,3,5)]
    result={'study':'Amazon Itupiranga, Pará; exploratory map review; no event confirmation',
      'summary':{'ru':'Среди четырёх пространственно разнесённых HV-кандидатов оптика не подтверждает однозначно новую вырубку; два пригодных для местного сравнения октябрьских снимка уточняют контекст, но не показывают однозначную SAR-причину.','en':'Across four spatially separated HV candidates, optical imagery does not unambiguously confirm new forest loss; two October scenes improve local context but do not establish the SAR cause.'},
      'selection':{'rule':'six valid native NISAR dates; median of Sep 4/16/28 minus median Jul 18/Aug 11/23 <= -3 dB and at least 2/3 post dates <= pre median -3 dB; 8-connected components were not required for the pixel screen; candidates thinned >=1 km; controls forest-class cells with smallest absolute shift, similarly thinned', 'candidate_count_screen':int(flags.sum()),'candidate_count_rule':'HV-only per-cell screen; 1,452 flagged. Not comparable to the earlier joint HH/HV dense component count of 83 under a different rule (which also applied component grouping).','displayed_candidates':len(candidates),'displayed_controls':len(controls),'screen_channel':'HV only','candidate_vs_joint_note':'This selection is HV-only. The stored joint3dbflag is an independent per-cell calculation requiring both HH and HV to meet <= -3 dB median shift and >=2/3 post persistence; it is not the selector for displayed candidates.'},
      'coordinate_mapping':'Dense native cell center: EPSG:32722 x=x_first+c*x_step, y=y_first+r*y_step -> WGS84 via pyproj. Optical crop center mapped using stored EPSG:4326 bounds of exact Sentinel-2 preview PNG (256x256). No sparse-to-dense point join performed.',
      'sar_inputs':[{'path':f'data/subsets/amazon-dense/{d}.npz','sha256':hashlib.sha256((ROOT/f'data/subsets/amazon-dense/{d}.npz').read_bytes()).hexdigest()} for d in DATES],
      'optical_scenes':[{'date':e['date'],'scene_id':e['scene_id'],'item_url':e['item_url'],'path':e['path'],'sha256':e['sha256'],'scl_clear_fraction':e['aoi_clear_fraction'],'scl_cloud_shadow_snow_fraction':e['aoi_cloud_shadow_snow_fraction']} for e in picks], 'maps':[]}
    # Contact-sheet cells: 128 px crops (~1.25 km square) from georeferenced 256 px AOI PNG.
    visual={
      ('candidate',29,66):('В июле и августе видны открытая светлая поверхность и линейные расчистки у лесо-полевой мозаики. 3 октября белая облачная область подходит к точке и закрывает часть окна; 21 октября точка лежит на уже открытом/мозаичном рисунке. Между чистыми участками дат не видно уверенно нового компактного просвета.','July and August show open pale ground and linear clearings at a forest/field mosaic edge. On October 3, a bright cloud approaches and partly obscures the target window; on October 21, the target lies in an already open/mosaic pattern. No confidently new compact opening is visible between clear portions of the dates.','Текущие карты не подтверждают новую расчистку; октябрьская сцена показывает существующий сельхозкрай, но окно 3 октября частично закрыто облаком. Влажностный/радарный эффект и мелкое изменение остаются возможными.','The maps do not confirm new clearing; the October scene shows an existing agricultural edge, while the October 3 window is partly cloud-obscured. Moisture/radar effects and small changes remain possible.','inconclusive','3 Oct local SCL clear fraction 0.809 (cloud-adjacent pixels may remain); 21 Oct 1.0. Global scene cloud percentage is not local quality.'),
      ('candidate',35,2):('Точка расположена у границы открытого участка и лесного пятна рядом с линейными просеками; октябрьские кадры показывают тот же открытый мозаичный рисунок. Чёрные области в новых contact sheets соответствуют SCL cloud/no-data.','The target is near an open-land/forest-patch margin and linear clearings; the October scenes show the same open mosaic pattern. Black areas in the new contact sheets are SCL cloud/no-data.','Новая вырубка не подтверждена: видимый рисунок в основном совпадает с ранее существовавшей границей; малое изменение полностью исключить нельзя.','New forest loss is not confirmed: the visible pattern largely follows a pre-existing boundary; a small change cannot be ruled out.','inconclusive','3 Oct local clear fraction 0.742 (cloud-limited, not valid context by the >=0.8 review threshold); 21 Oct 1.0. Original PNG crop also had edge no-data.'),
      ('candidate',34,133):('В июльских и октябрьских окнах видна открытая мозаика с изогнутой древесной полосой; небольшое тёмное пятно северо-западнее креста повторяется на 3 и 21 октября. Нового отчётливого пятна в точке не видно.','July and October windows show open mosaic with a curved wooded strip; a small dark spot northwest of the cross recurs on October 3 and 21. No distinct new patch is visible at the target.','Повторяющийся тёмный объект и существующая мозаика не дают визуального свидетельства новой потери леса; природа SAR-сдвига остаётся неизвестной.','The recurring dark feature and existing mosaic provide no visual evidence of new forest loss; the cause of the SAR shift remains unknown.','not_visually_confirmed','3 Oct local SCL clear fraction 0.997; 21 Oct 1.0. RGB appearance is qualitative and not an index.'),
      ('candidate',129,71):('На 21 октября крест в непрерывно выглядящем древесном пологе у неровной границы; заметного нового просвета не видно. 3 октября видимые участки также лесные, но часть окна закрыта облаком/no-data.','On October 21, the cross lies in apparently continuous canopy at an irregular edge; no obvious new opening is visible. Visible portions on October 3 are also wooded, but part of that window is cloud/no-data.','Поздняя чистая оптика не подтверждает новую потерю леса в этой точке; это не исключает малый/кратковременный или иным образом неразрешимый радарный эффект.','The later clear optical image does not confirm new forest loss at this point; a small/transient or otherwise unresolved radar effect is not excluded.','not_visually_confirmed','3 Oct local SCL clear fraction 0.489: unusable as complete context; 21 Oct 1.0 and is the useful post-Sep-28 comparison.'),
      ('control',106,101):('Преимущественно древесный покров с уже существующей периферийной линией/просекой; на 21 октября покров выглядит непрерывным.','Mostly wooded cover with an established perimeter line/clearing; canopy appears continuous on October 21.','Контекстный пример малой HV-разности, не проверенная отрицательная метка и не доказательство отсутствия события.','A low-HV-shift context example, not a verified negative label or evidence that no event occurred.','control_context','3 Oct local SCL clear fraction 0.549 (cloud-limited); 21 Oct 1.0. Control выбран по малому SAR-сдвигу, не ground truth.'),
      ('control',107,51):('Текстурно однородный лесной интерьер; на 21 октября виден сплошной древесный покров, явного нового пятна нет.','Texturally homogeneous forest interior; continuous wooded cover is visible on October 21, with no obvious new patch.','Описательный контроль, не верифицированный negative.','Descriptive control, not a verified negative.','control_context','3 Oct local SCL clear fraction 0.962; 21 Oct 1.0. Это не независимо проверенная отрицательная метка.'),
      ('control',28,94):('Открытая сельскохозяйственная/расчищенная мозаика с широкими существующими границами; на 21 октября точечная новая расчистка не выделяется.','Open agricultural/cleared mosaic with broad existing boundaries; no point-centered new clearing stands out on October 21.','Контекст показывает неоднородность уже открытого/сельхозного ландшафта при малом SAR-сдвиге; причинная роль не установлена.','This context illustrates heterogeneity in already open/agricultural land despite a small SAR shift; no cause is established.','control_context','3 Oct local SCL clear fraction 0.998; 21 Oct 1.0. Descriptive, not matched or verified control.'),
      ('control',60,1):('На стыке леса и открытого участка видны старые ветвящиеся линии; 3 октября окно частично закрыто облаком, 21 октября рисунок границ сохраняется.','Old branching lines are visible at the forest/open-land edge; the October 3 window is partly clouded, and the boundary pattern persists on October 21.','Нельзя трактовать как verified negative; поздняя чистая дата не показывает очевидного нового точечного пятна.','Do not treat as a verified negative; the later clear date shows no obvious new point-centered patch.','control_context','3 Oct local SCL clear fraction 0.451 (cloud-limited); 21 Oct 1.0. No independent negative label.')}
    source_fingerprint=hashlib.sha256(json.dumps([x['sha256'] for x in [{'sha256':e['sha256']} for e in picks]],separators=(',',':')).encode()).hexdigest()
    result['maps']=[]
    for role, coords in [('candidate',candidates),('control',controls)]:
      for j,(r,c) in enumerate(coords,1):
        x=g['x_first']+c*g['x_step']; y=g['y_first']+r*g['y_step']; lon,lat=to_geo(x,y)
        tiles=[]
        for e in picks:
          im=Image.open(ROOT/e['path']).convert('RGBA'); b=e['bounds']; px=(lon-b['w'])/(b['e']-b['w'])*im.width; py=(b['n']-lat)/(b['n']-b['s'])*im.height
          half=34; crop=im.crop((round(px-half),round(py-half),round(px+half),round(py+half))).resize((204,204))
          d=ImageDraw.Draw(crop); d.line((96,102,108,102),fill='red',width=2); d.line((102,96,102,108),fill='red',width=2)
          tiles.append(crop)
        sheet=Image.new('RGB',(204*len(tiles),236),'white'); draw=ImageDraw.Draw(sheet)
        for k,(im,e) in enumerate(zip(tiles,picks)):
          sheet.paste(im,(k*204,26)); draw.text((k*204+3,5),e['date'],fill='black')
        name=f'{role}-{j:02d}.png'; sheet.save(OUT/'maps'/name,optimize=True)
        series={}
        for channel,values,vm in [('HH',hh_db,hh_valid),('HV',db,valid)]:
          series[channel]=[float(values[k,r,c]) if vm[k,r,c] else None for k in range(len(DATES))]
        change_hh=float(hh_change[r,c]) if hhv[r,c] else None
        idx={'id':f'{role}-{j:02d}','role':role,'native_row':r,'native_col':c,'lat':lat,'lon':lon,
          'coordinate_fingerprint':hashlib.sha256(f'EPSG:32722|{r}|{c}|{x:.3f}|{y:.3f}'.encode()).hexdigest(),
          'worldcover2021_code':int(cover[r,c]),'sar_series_db':{'dates':DATES,'HH':series['HH'],'HV':series['HV']},
          'hv_shift_db':float(change[r,c]),'hh_companion_shift_db':change_hh,
          'joint3dbflag':bool(joint_flags[r,c]),'joint3dbflag_rule':'both HH and HV median Sep 4/16/28 minus median Jul 18/Aug 11/23 <= -3 dB and each band individually <= own pre median -3 dB on at least 2 of 3 post dates; six observations valid in both bands',
          'optical_contact_sheet':f'data/investigation/maps/{name}','sha256':hashlib.sha256((OUT/'maps'/name).read_bytes()).hexdigest(),
          'visual_annotation_key':{'native_row':r,'native_col':c,'contact_sheet_sha256':hashlib.sha256((OUT/'maps'/name).read_bytes()).hexdigest(),'optical_source_fingerprint':source_fingerprint}}
        note=visual.get((role,r,c))
        if note:
          idx.update({'observation':{'ru':note[0],'en':note[1]},'interpretation':{'ru':note[2],'en':note[3]},'status':note[4], 'limitations':note[5]})
        else: idx['status']='unreviewed'
        result['maps'].append(idx)
    receipt_path=OUT/'maps/new-optical-receipts.json'
    if receipt_path.exists():
      receipt=json.loads(receipt_path.read_text())
      result['new_optical_evidence']={'receipt':'data/investigation/maps/new-optical-receipts.json',
        'query':receipt.get('query'),'catalogue_status':receipt.get('catalogue_status'),
        'selected_scenes':[{'date':s['date'],'scene_id':s['scene_id'],'item_url':s['item_url'],
          'scene_cloud_percent':s['scene_cloud_percent'],'processing_metadata':s['processing_metadata'],'assets':s['assets'],
          'bounds_m':s['bounds_m'],'scl':s['scl'],'scl_clear_by_point':s['scl_clear_by_point'],
          'asset_npz':s['asset_npz'],'asset_npz_sha256':s['asset_npz_sha256'],
          'native_analysis_grid':s['native_analysis_grid'],'calibration':s['calibration'],
          'mask':s['mask'],'indices':s['indices']} for s in receipt.get('selected_scenes',[])],
        'attempts':receipt.get('attempts',[])}
      for item in result['maps']:
        item['new_optical']=[{'date':scene['date'],'scene_id':scene['scene_id'],
          'local_scl_clear_fraction':next((q['clear_fraction'] for q in scene['scl_clear_by_point'] if q['id']==item['id']),None),
          'context_status':'usable_local_context' if next((q['clear_fraction'] for q in scene['scl_clear_by_point'] if q['id']==item['id']),0)>=.8 else 'cloud_limited_context',
          'metrics':next((q for q in scene['point_crops'] if q['id']==item['id']),None)}
          for scene in receipt.get('selected_scenes',[])]
        sheets=receipt.get('new_contact_sheets',[])
        contact=next((x for x in sheets if x['id']==item['id']),None)
        source_assets=[]
        for scene in receipt.get('selected_scenes',[]):
          point=next((x for x in scene.get('point_crops',[]) if x['id']==item['id']),None)
          if point: source_assets.append({'date':scene['date'],'scene_id':scene['scene_id'],'path':point['rgb_path'],'sha256':point['rgb_sha256'],'item_url':scene['item_url']})
        item['new_optical_contact_sheet']=contact
        item['visual_annotation_key'].update({'coordinate_fingerprint':item['coordinate_fingerprint'],
          'new_contact_sheet_sha256':contact['sha256'] if contact else None,'new_source_images':source_assets,
          'source_fingerprint':hashlib.sha256(json.dumps({'coordinate':item['coordinate_fingerprint'],
            'old_contact_sheet':item['sha256'],'old_source_fingerprint':source_fingerprint,'new_contact':contact,
            'new_source_images':source_assets},sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    (OUT/'map-candidates.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'screen':int(flags.sum()),'candidates':result['maps']},indent=2))
if __name__=='__main__': main()
