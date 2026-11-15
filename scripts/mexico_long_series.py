"""Полный аудит 54 GUNW: связные окна, кандидаты опоры и границы оценки скорости.

python -m scripts.mexico_long_series
Не заменяет нулями отсутствующие измерения и не переносит опору через разрывы.
"""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np

from scripts import mexico_displacement as M

OUTPUT='data/analysis/mexico-long-series.json'
GNSS='data/analysis/mexico-mmx1-long-gnss.json'


def refresh_opera_catalogue():
    import requests
    params={'collection_concept_id':'C3294057315-ASF','bounding_box':'-99.09,19.415,-99.065,19.44',
            'page_size':2000,'sort_key':'-start_date'}
    response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90)
    response.raise_for_status();entries=response.json()['feed']['entry'];hits=int(response.headers['CMR-Hits'])
    if hits!=len(entries):raise ValueError('Нужна пагинация OPERA')
    rows=[]
    for g in entries:
        name=g['producer_granule_id'];f=name.split('_')
        url=next((v['href'] for v in g.get('links',[]) if v['href'].startswith('https:') and v['href'].endswith('.nc')
                  and v.get('rel','').endswith('/data#')),None)
        rows.append({'id':name,'concept_id':g['id'],'url':url,'reference':f[6][:8],'secondary':f[7][:8],'frame':f[4]})
    M.save('data/evidence/mexico-opera-full-catalogue.json',{'query':response.url,
           'checked_at':datetime.now(timezone.utc).isoformat(),'hits':hits,'granules':rows})


def refresh_gnss():
    """Публичные суточные решения NGL, только интервал каталога GUNW."""
    import requests
    url='https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/MMX1.tenv3'
    response=requests.get(url,timeout=90);response.raise_for_status()
    lines=response.text.splitlines();selected=[];records=[]
    for line in lines[1:]:
        f=line.split()
        if len(f)<23 or f[0]!='MMX1':continue
        day=datetime.strptime(f[1],'%y%b%d').date().isoformat()
        if not '2025-10-30'<=day<='2026-10-20':continue
        record={'date':day,'east_m':float(f[7])+float(f[8]),'north_m':float(f[9])+float(f[10]),
                'up_m':float(f[11])+float(f[12]),'sigma_up_m':float(f[16])}
        if not all(np.isfinite(v) for k,v in record.items() if k!='date'):raise ValueError('Неконечные GNSS значения')
        selected.append(line);records.append(record)
    records.sort(key=lambda r:r['date'])
    if not records or len({r['date'] for r in records})!=len(records):raise ValueError('Нет GNSS или повторные даты')
    raw=M.ROOT/'data/subsets/mmx1-gnss/2025-10-30_2026-10-20.tenv3'
    raw.write_text(lines[0]+'\n'+'\n'.join(selected)+'\n')
    M.save(GNSS,{'station':'MMX1','source_url':url,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
                 'subset_path':raw.relative_to(M.ROOT).as_posix(),'sha256':M.digest(raw),'records':records,
                 'limitations':'Антенна GNSS в IGS20; не является независимой неподвижной опорой для всей AOI.'})


def days(a,b):
    return (date.fromisoformat(b)-date.fromisoformat(a)).days


def load_all():
    hashes={}
    catalogue=M.read(M.CATALOGUE,hashes)
    site=M.read('data/mexico.json',hashes)
    coords=np.array([(p['lat'],p['lon']) for p in site['pixels']])
    wanted={g['id']:g for g in catalogue['granules']}; found={}; pairs={d:[] for d in M.SPECS}
    for directory in ['mexico-gunw-series','mexico-gunw-remaining']:
        for path in sorted((M.ROOT/'data/subsets'/directory).glob('*/*.json')):
            r=M.read(path.relative_to(M.ROOT),hashes); ident=r['identification']; sid=r['source']['id']
            if sid not in wanted or sid in found:raise ValueError('Лишняя или повторная гранула')
            g=wanted[sid]; d=g['direction']; track,frame,word,_=M.SPECS[d]
            if (ident['track'],ident['frame'],ident['direction'],ident['look_direction'])!=(track,frame,word,'Left'):
                raise ValueError('Несовместимая геометрия')
            if r['source']['concept_id']!=g['concept_id'] or r['source']['url']!=g['url']:
                raise ValueError('Гранула не совпадает с каталогом')
            if r['grid']['epsg']!=32614 or r['grid']['spacing']!=[80.,-80.]:
                raise ValueError('Несовместимая native сетка')
            file=M.ROOT/r['subset_path']
            if M.digest(file)!=r['sha256']:raise ValueError('Нарушена контрольная сумма')
            hashes[r['subset_path']]=r['sha256']
            with np.load(file) as f:a={k:f[k] for k in f.files}
            required=['phase','iono','iono_sd','mask','component','coherence','lat','lon']
            if any(a[k].shape!=(32,32) for k in required) or not np.array_equal(np.stack([a['lat'].ravel(),a['lon'].ravel()],axis=1),coords):
                raise ValueError('Координаты или размерность различаются')
            if int(M.quality(a).sum())!=r['quality_valid_count']:raise ValueError('Маска не совпадает с квитанцией')
            if r['reference_date']>=r['secondary_date']:raise ValueError('Обратные даты')
            found[sid]=path.relative_to(M.ROOT).as_posix()
            pairs[d].append({'receipt':r,'arrays':a,'receipt_path':found[sid]})
    missing=sorted(set(wanted)-set(found))
    if missing:raise ValueError(f'Не прочитаны {len(missing)} гранул; полный аудит не сформирован')
    for rows in pairs.values():rows.sort(key=lambda p:(p['receipt']['reference_date'],p['receipt']['secondary_date']))
    return pairs,hashes,site


def windows(pairs):
    """Все последовательные окна, а не только прошедшее отбор самое удачное."""
    out=[]
    for start in range(len(pairs)):
        for stop in range(start+1,len(pairs)+1):
            sub=pairs[start:stop]
            if len(sub)>1 and sub[-2]['receipt']['secondary_date']!=sub[-1]['receipt']['reference_date']:break
            mask,_=M.connected_intersection(sub)
            ref,sec=sub[0]['receipt']['reference_date'],sub[-1]['receipt']['secondary_date']
            out.append({'start_index':start,'stop_index':stop,'reference_date':ref,'secondary_date':sec,
                        'days':days(ref,sec),'pairs':len(sub),'common_points':int(mask.sum())})
    return out


def longest(rows,minimum_points):
    usable=[r for r in rows if r['common_points']>=minimum_points]
    return max(usable,key=lambda r:(r['days'],r['common_points'],-r['start_index'])) if usable else None


def diagnose_reference(pairs,window):
    if window is None:return {'available':False,'stable_reference_verified':False}
    selected=pairs[window['start_index']:window['stop_index']]
    mask,labels=M.connected_intersection(selected)
    rr,cc=np.indices(mask.shape)
    references={'all_common':mask}
    sector_counts={}
    signatures={mask.tobytes()}
    for name,sector in {'NW':(rr<16)&(cc<16),'NE':(rr<16)&(cc>=16),'SW':(rr>=16)&(cc<16),'SE':(rr>=16)&(cc>=16)}.items():
        sector_counts[name]=int((mask&sector).sum())
        candidate=mask&sector
        if sector_counts[name]>=3 and candidate.tobytes() not in signatures:
            references[name]=candidate;signatures.add(candidate.tobytes())
    # Если все точки лежат в одном квадранте, сравнение его с общей маской тождественно.
    # Дополнительно делим пространственный bbox принятых точек, без отбора по смещению.
    row,col=np.nonzero(mask);r_mid=(row.min()+row.max())/2;c_mid=(col.min()+col.max())/2
    for name,sector in {'local_N':rr<=r_mid,'local_S':rr>r_mid,'local_W':cc<=c_mid,'local_E':cc>c_mid}.items():
        candidate=mask&sector
        if candidate.sum()>=3 and candidate.tobytes() not in signatures:
            references[name]=candidate;signatures.add(candidate.tobytes())
    series={}
    for name,ref in references.items():series[name],_=M.chain(selected,mask,ref)
    baseline=series['all_common']
    dates=[selected[0]['receipt']['reference_date']]+[p['receipt']['secondary_date'] for p in selected]
    shifts={name:[float(np.median((v[t]-baseline[t])[mask])) for t in range(len(v))] for name,v in series.items()}
    flattened=sum(all(str(v).lower()=='true' for v in p['receipt']['grid'].get('flattening',{}).values())
                  and len(p['receipt']['grid'].get('flattening',{}))==2 for p in selected)
    result={'available':True,'selection':window,'dates':dates,'target_indices':np.flatnonzero(mask).tolist(),
            'component_signature':labels,'reference_sector_counts':sector_counts,'reference_shift_cm':shifts,
            'distinct_reference_sets':len(references),
            'reference_indices':{k:np.flatnonzero(v).tolist() for k,v in references.items()},
            'reference_sensitivity_available':len(references)>1,
            'endpoint_reference_shift_range_cm':float(np.ptp([v[-1] for v in shifts.values()])),
            'diagnostic_cm_by_epoch':[M.summary(v) for v in baseline],
            'flattening_verified_pairs':int(flattened),
            'geometry_saved_pairs':sum(p['receipt']['grid'].get('geometry',{}).get('available',False) for p in selected),
            'stable_reference_verified':False,'external_immobile_control_points':0,
            'stability_limit':'Сквозная когерентность и малый разброс относительных опор не исключают общий дрейф всей AOI.',
            'relative_rate_fit':{'available':False,'reason':'Для исследовательского линейного наклона требуется >=8 реальных вторичных эпох и >=90 дней; это не критерий подтверждённой скорости.'}}
    # Начальный условный ноль не считается независимым наблюдением регрессии.
    if len(selected)>=8 and days(dates[1],dates[-1])>=90:
        t=np.array([days(dates[1],d)/365.25 for d in dates[1:]])
        x=t-t.mean(); y=baseline[1:,mask]
        slope=(x[:,None]*(y-y.mean(axis=0))).sum(axis=0)/(x*x).sum()
        residual=y-(y.mean(axis=0)+x[:,None]*slope)
        ref_slopes={}
        for name,values in shifts.items():
            shift=np.array(values[1:])
            ref_slopes[name]=float((x*(shift-shift.mean())).sum()/(x*x).sum())
        jackknife=[]
        for leave in range(len(t)):
            keep=np.arange(len(t))!=leave;xx=t[keep]-t[keep].mean(); yy=y[keep]
            jackknife.append((xx[:,None]*(yy-yy.mean(axis=0))).sum(axis=0)/(xx*xx).sum())
        result['relative_rate_fit']={'available':True,'quantity':'Исследовательский наклон относительного LOS, см/год; не подтверждённая скорость грунта.',
            'real_secondary_epochs':len(selected),'fit_span_days':days(dates[1],dates[-1]),'slope_cm_per_year':M.summary(slope),
            'reference_slope_shift_cm_per_year':ref_slopes,
            'reference_slope_shift_range_cm_per_year':float(np.ptp(list(ref_slopes.values()))),
            'residual_rms_cm':M.summary(np.sqrt(np.mean(residual*residual,axis=0))),
            'leave_one_epoch_slope_range_cm_per_year':M.summary(np.ptp(np.array(jackknife),axis=0)),
            'systematic_uncertainty':'Не оценена: атмосфера, ковариация и внешняя неподвижность опоры не проверены.',
            'validated':False}
    return result


def calculate():
    pairs,hashes,site=load_all()
    report={'schema_version':1,'kind':'full_catalogue_gunw_quality_and_reference_audit',
            'input_sha256':hashes,'implementation_sha256':{'audit':M.digest(Path(__file__)),'core':M.digest(Path(M.__file__))},
            'sources':M.DOCS,'sample_count':1024,'catalogue_complete':True,'downloaded_additional_pairs':38,
            'directions':{},'reference_search_scope':'Прежняя AOI 0,025° × 0,025°. Проверена доступность фиксированных областей; геологическая неподвижность не выводится из когерентности.',
            'criteria':'Без изменения прежних масок; все последовательные окна. Кандидат опоры: >=10 сквозных точек. Длинное диагностическое окно: >=90 дней и >=8 пар. Эти рабочие пороги не доказывают неподвижность или точность.'}
    for direction,rows in pairs.items():
        ww=windows(rows); candidate=longest(ww,10)
        data=[]
        for p in rows:
            r,a=p['receipt'],p['arrays'];ok=M.quality(a);sw=a['mask']&255
            data.append({'reference_date':r['reference_date'],'secondary_date':r['secondary_date'],
                'source':r['source'],'receipt':p['receipt_path'],'valid':int(ok.sum()),
                'individual_check_counts':{k:int(v.sum()) for k,v in M.quality_checks(a).items()},
                'ionosphere_interpolated_accepted':int((ok&((a['mask']&(1<<24))!=0)).sum())})
        report['directions'][direction]={'sampled_pairs':data,'count':len(rows),
            'span':[rows[0]['receipt']['reference_date'],rows[-1]['receipt']['secondary_date']],
            'all_pairs_common':int(M.connected_intersection(rows)[0].sum()),
            'zero_quality_pairs':sum(p['valid']==0 for p in data),'windows':ww,
            'longest_by_minimum_points':{str(n):longest(ww,n) for n in [1,3,10,30,100]},
            'long_windows_with_10_points':sum(w['days']>=90 and w['pairs']>=8 and w['common_points']>=10 for w in ww),
            'reference_diagnosis':diagnose_reference(rows,candidate)}
    # Проверяем альтернативные длинные окна обоих направлений, а не только два максимума.
    long_masks={}
    for d,rows in pairs.items():
        long_masks[d]=[]
        for w in report['directions'][d]['windows']:
            if w['days']>=90 and w['pairs']>=8 and w['common_points']>=1:
                mask,_=M.connected_intersection(rows[w['start_index']:w['stop_index']])
                long_masks[d].append((w,mask))
    joint=[]
    for a,ma in long_masks['ascending']:
        for d,md in long_masks['descending']:
            start=max(a['reference_date'],d['reference_date']);end=min(a['secondary_date'],d['secondary_date'])
            overlap=max(0,days(start,end))
            if overlap>=90:
                joint.append({'ascending':[a['reference_date'],a['secondary_date']],
                              'descending':[d['reference_date'],d['secondary_date']],
                              'overlap_days':overlap,'shared_points':int((ma&md).sum())})
    selected_masks=[]
    for v in report['directions'].values():
        indices=v['reference_diagnosis'].get('target_indices',[])
        mask=np.zeros(1024,bool);mask[indices]=True;selected_masks.append(mask)
    report['decomposition']={'available':False,
        'shared_points_in_individually_longest_windows':int((selected_masks[0]&selected_masks[1]).sum()),
        'long_window_combinations_with_90_day_overlap':len(joint),
        'maximum_shared_points_in_any_long_combination':max((v['shared_points'] for v in joint),default=0),
        'best_combinations':sorted(joint,key=lambda x:(x['shared_points'],x['overlap_days']),reverse=True)[:10],
        'stable_common_reference_verified':False,
        'reason':'Для двух LOS нужны общие надёжные координаты и согласованная внешняя опора; сама геометрия не восстанавливает отсутствующие измерения. Отдельные даты могут различаться при обоснованной модели движения.'}
    # Проверка независимого OPERA: только реально сохранённые наблюдения, без экстраполяции.
    op,dates,values=M.opera_data(hashes,np.array([(p['lat'],p['lon']) for p in site['pixels']]))
    comparisons={}
    for direction,v in report['directions'].items():
        selected=v['reference_diagnosis'].get('selection')
        if not selected:comparisons[direction]={'available':False};continue
        idx,offset,accepted=M.nearest_interval(dates,selected['reference_date'],selected['secondary_date'])
        comparisons[direction]={'nisar_dates':[selected['reference_date'],selected['secondary_date']],
            'nearest_opera_dates':[dates[i] for i in idx],'offset_days':offset,
            'both_endpoints_within_3_days':accepted,'independent_physical_validation':False,
            'reason':'Нет подтверждённой внешней опоры и обработки атмосферы; совпадение интервалов не доказывает согласие.'}
    report['opera']={'observed_dates':len(dates),'span':[dates[0],dates[-1]],'longest_window_comparison':comparisons,
                     'independent_validation':False,'previous_short_interval_comparison':'data/analysis/mexico-displacement-audit.json'}
    op_catalogue=M.read('data/evidence/mexico-opera-full-catalogue.json',hashes)
    same_frame=[g for g in op_catalogue['granules'] if g['frame']==op['frame']]
    report['opera']['catalogue_complete']=op_catalogue['hits']==len(op_catalogue['granules'])
    report['opera']['frame_catalogue_count']=len(same_frame)
    report['opera']['latest_catalogue_secondary']=max(g['secondary'] for g in same_frame)
    report['opera']['catalogue_coverage_by_frame']={f:{'granules':sum(g['frame']==f for g in op_catalogue['granules']),
            'latest_secondary':max(g['secondary'] for g in op_catalogue['granules'] if g['frame']==f)}
            for f in sorted({g['frame'] for g in op_catalogue['granules']})}
    report['opera']['catalogue_latest_secondary_all_frames']=max(g['secondary'] for g in op_catalogue['granules'])
    gnss=M.read('data/analysis/mexico-mmx1-gnss.json',hashes);i=gnss['nearest_nisar_sample']['index']
    report['gnss']={'station':gnss['station'],'distance_m':gnss['nearest_nisar_sample']['distance_m'],
        'passes_by_direction':{d:sum(bool(M.quality(p['arrays']).ravel()[i]) for p in rows) for d,rows in pairs.items()},
        'stable_reference_verified':False}
    report['gnss']['passes_in_longest_candidate']={}
    for d,rows in pairs.items():
        w=report['directions'][d]['reference_diagnosis'].get('selection')
        if w:
            selected=rows[w['start_index']:w['stop_index']]
            report['gnss']['passes_in_longest_candidate'][d]={'accepted':sum(bool(M.quality(p['arrays']).ravel()[i]) for p in selected),
                                                           'pairs':len(selected)}
    long_gnss=M.read(GNSS,hashes)
    raw=M.ROOT/long_gnss['subset_path']
    if M.digest(raw)!=long_gnss['sha256']:raise ValueError('GNSS SHA-256 не совпадает')
    hashes[long_gnss['subset_path']]=long_gnss['sha256']
    records=long_gnss['records'];t=np.array([days(records[0]['date'],r['date'])/365.25 for r in records])
    slopes={k:float(np.polyfit(t,[r[k]*100 for r in records],1)[0]) for k in ['east_m','north_m','up_m']}
    report['gnss']['long_window']={'records':len(records),'span':[records[0]['date'],records[-1]['date']],
        'linear_slopes_cm_per_year':slopes,'up_last_minus_first_cm':(records[-1]['up_m']-records[0]['up_m'])*100,
        'interpretation':'Наклоны суточных GNSS решений; не оценка стабильности других опор. Формальная ошибка OLS не выдаётся за систематическую.'}
    report['ui']={'status':'insufficient_for_validated_velocity','velocity_available':False,'vertical_east_available':False,
        'message_ru':f"Проверены все 54 пары GUNW (ещё 38 загружены через Earthdata). Сквозных точек на полном интервале: {report['directions']['ascending']['all_pairs_common']}/{report['directions']['descending']['all_pairs_common']}. Внешняя стабильная опора не подтверждена. Подтверждённая скорость и вертикальное разложение недоступны.",
        'report':'docs/mexico-long-series.md'}
    return report


def write_outputs(r):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    target=M.ROOT/'docs/figures/mexico-long-series';target.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(2,1,figsize=(13,7),layout='constrained')
    for ax,(direction,v) in zip(axes,r['directions'].items()):
        rows=v['sampled_pairs'];x=np.arange(len(rows));ax.bar(x,[p['valid'] for p in rows],color='#206695')
        for i,p in enumerate(rows):ax.text(i,p['valid']+10,str(p['valid']),ha='center',fontsize=7)
        ax.set_xticks(x[::2],[p['reference_date'] for p in rows[::2]],rotation=30,ha='right')
        ax.set_ylim(0,1050);ax.set_ylabel('Точек из 1024');ax.set_title(f"{direction}: {len(rows)} пар, нулевых — {v['zero_quality_pairs']}")
    fig.suptitle('Все 54 GUNW: исходные маски, пороги не изменены');fig.savefig(target/'full-quality.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,(direction,v) in zip(axes,r['directions'].items()):
        ww=v['windows'];ax.scatter([w['days'] for w in ww],[w['common_points'] for w in ww],s=12,alpha=.45)
        ax.axvline(90,color='#b15b22',ls='--',label='90 дней: рабочий порог');ax.axhline(10,color='grey',ls=':',label='10 точек')
        ax.set_xlabel('Длительность окна, дней');ax.set_ylabel('Сквозных точек');ax.set_title(direction);ax.legend(fontsize=8)
    fig.suptitle('Все окна: достаточная длина не подтверждает стабильность опоры');fig.savefig(target/'windows.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(direction,v) in enumerate(r['directions'].items()):
        diag=v['reference_diagnosis']
        if not diag['available']:
            for ax in axes[:,col]:ax.text(.5,.5,'Нет области опоры',transform=ax.transAxes,ha='center')
            continue
        t=[date.fromisoformat(d) for d in diag['dates']]
        q=np.array([x['p05_p50_p95'] for x in diag['diagnostic_cm_by_epoch']])
        axes[0,col].fill_between(t,q[:,0],q[:,2],alpha=.2,label='5–95% точек, не ошибка')
        axes[0,col].plot(t,q[:,1],'o-',label='Медиана относительного LOS')
        axes[0,col].set_ylabel('Диагностическое LOS, см');axes[0,col].set_title(direction)
        axes[0,col].legend(fontsize=8)
        for name,shift in diag['reference_shift_cm'].items():axes[1,col].plot(t,shift,'o-',label=name)
        axes[1,col].set_ylabel('Сдвиг при смене опоры, см');axes[1,col].legend(fontsize=8)
        for ax in axes[:,col]:ax.tick_params(axis='x',rotation=25);ax.axhline(0,color='grey',lw=.7)
    fig.suptitle('Самые длинные окна с ≥10 точками: внешняя стабильность опоры не установлена')
    fig.savefig(target/'reference.png',dpi=150);plt.close(fig)
    lines=[];reference_lines=[];comparison_lines=[];continuity_lines=[]
    for d,v in r['directions'].items():
        w=v['longest_by_minimum_points']['10']
        lines.append(f"| {d} | {v['count']} | {v['zero_quality_pairs']} | {v['all_pairs_common']} | {w['days'] if w else 0} | {w['common_points'] if w else 0} |")
        diag=v['reference_diagnosis']
        if w:
            reference_lines.append(f"- {d}: {w['reference_date']} → {w['secondary_date']}, {w['pairs']} пар, {w['common_points']} точек. Смена квадрантной опоры сдвигает конечное относительное смещение на {diag['endpoint_reference_shift_range_cm']:.3f} см; это не доверительный интервал.")
        fit=diag.get('relative_rate_fit',{})
        if fit.get('available'):
            q=fit['slope_cm_per_year']['p05_p50_p95']
            reference_lines.append(f"  Исследовательский наклон LOS: медиана {q[1]:.3f} см/год, пространственные 5–95% {q[0]:.3f}…{q[2]:.3f}; реальных вторичных эпох — {fit['real_secondary_epochs']}, продолжительность — {fit['fit_span_days']} дн. Внешняя стабильность и систематическая ошибка не установлены; это не подтверждённая скорость.")
            reference_lines.append(f"  Диапазон сдвига наклона при смене опоры: {fit['reference_slope_shift_range_cm_per_year']:.3f} см/год. Также сохранена чувствительность к исключению одной эпохи; ни один из этих диапазонов не является доверительным интервалом.")
        else:reference_lines.append(f"- {d}: даже исследовательская регрессия по принятому критерию не рассчитана: {fit.get('reason','нет окна')}.")
    for minimum in ['1','3','10','30','100']:
        spans=[]
        for v in r['directions'].values():
            w=v['longest_by_minimum_points'][minimum]
            spans.append(str(w['days']) if w else 'нет')
        continuity_lines.append(f"| {minimum} | {' | '.join(spans)} |")
    for d,p in r['opera']['longest_window_comparison'].items():
        if 'offset_days' in p:
            comparison_lines.append(f"- {d}: NISAR {' → '.join(p['nisar_dates'])}; ближайшие OPERA {' → '.join(p['nearest_opera_dates'])}; смещения дат {p['offset_days']} суток. Оба конца в пределах трёх суток: {'да' if p['both_endpoints_within_3_days'] else 'нет'}.")
    gnss=r['gnss']['long_window']
    text=f'''# Мехико: полная догрузка GUNW и проверка длинного ряда

Догружены native окна **38/38** оставшихся гранул Earthdata; вместе с прежними
16 проверены **все 54** гранулы сохранённого каталога PROVISIONAL V1. Полные HDF5
не копируются: сохраняются исходные окна AOI, метаданные и контрольные суммы.

| Направление | Пар | Нулевых пар | Точек сквозь все пары | Самое длинное окно с ≥10 точками, дней | Точек в нём |
|---|---:|---:|---:|---:|---:|
{chr(10).join(lines)}

Чувствительность результата к минимальному числу сквозных точек:

| Минимум точек | Длиннейшее ascending окно, дней | Длиннейшее descending окно, дней |
|---:|---:|---:|
{chr(10).join(continuity_lines)}

![Прохождение строгих масок](figures/mexico-long-series/full-quality.png)

![Все связные окна](figures/mexico-long-series/windows.png)

Окна перебраны полностью, без отбора по направлению или величине смещения.
Проверены SHA-256, координаты, даты, направление, frame/track и одинаковая маска.
Номера компонент между парами независимы: проверяется их совместная комбинация.
Порог coherence 0,7 и uncertainty ≤1 рад сохранён. Разрывы и отклонённые точки
не заполняются. Начальный условный ноль не считается наблюдением регрессии.

Для каждого направления JSON содержит самые длинные окна с минимум 1/3/10/30/100
сквозными точками, диагностику фиксированных квадрантных опор и атмосферных
ограничений. Рабочие пороги длинного окна — 90 дней и 8 пар — не являются
доказательством точности или стабильности. Кандидат с ≥10 точками выбирается
по длине, затем по числу точек; это исследовательский, ретроспективный отбор.
Для исследовательской регрессии дополнительно требуются минимум 90 дней между
реальными вторичными эпохами; условный начальный ноль этот интервал не увеличивает.

**Опора:** неподвижных внешних контрольных точек в этом расчёте не установлено.
Сходство фаз, высокая когерентность и малое расхождение квадрантов не исключают
совместное проседание всей AOI или атмосферный остаток. Поиск выполнен в прежней
AOI 0,025° × 0,025°; утверждение об отсутствии стабильного грунта во всём Мехико
не делается. GNSS MMX1 не объявляется неподвижной опорой.
Сравниваются только разные наборы опорных координат. Дополнительно к квадрантам
AOI используются северная/южная и западная/восточная половины bbox сквозных
точек; минимум три точки на опору. Границы зависят от координат и маски,
не от величины смещения. Тождественные наборы удалены из сравнения.

{chr(10).join(reference_lines)}

![Диагностика длинных рядов и смены опоры](figures/mexico-long-series/reference.png)

Внешний контроль MMX1: суточных решений — **{gnss['records']}**, интервал —
{' → '.join(gnss['span'])}; изменение up между первой и последней датами
**{gnss['up_last_minus_first_cm']:.2f} см**, линейный наклон up
**{gnss['linear_slopes_cm_per_year']['up_m']:.2f} см/год**. Это движение антенны
GNSS в IGS20, не скорость NISAR и не неподвижная опора. Ближайшая радарная
точка проходит {r['gnss']['passes_by_direction']['ascending']}/28 ascending и
{r['gnss']['passes_by_direction']['descending']}/26 descending масок.

Если окно позволяет линейную регрессию, её относительный наклон и ограничения
отдельно записаны в `relative_rate_fit`. Это не подтверждённая скорость грунта.
Для новых гранул сохранены фактические flattening flags и исходные LOS ENU кубы
на всех высотах. Кубы не подменены произвольной высотой местности. Ионосфера
вычитается; тропосфера и приливы не исправлены, систематическая ошибка неизвестна.

**OPERA:** проверены ближайшие реальные даты для обоих концов самых длинных окон
с допуском три дня. Сохранённые 15 OPERA дат покрывают {r['opera']['span'][0]} —
{r['opera']['span'][1]}; экстраполяция не используется. Физическое согласие
скоростей не заявляется без согласованной опоры, геометрии и обработки атмосферы.
Сравнение прежних коротких интервалов сохранено [в первом расчёте](mexico-displacement.md).

Полный свежий каталог OPERA проверен по всем {len(json.loads((M.ROOT/'data/evidence/mexico-opera-full-catalogue.json').read_text())['granules'])}
динамическим гранулам над AOI, из них {r['opera']['frame_catalogue_count']} относятся
к F01088. Последняя secondary date этого кадра — **{datetime.strptime(r['opera']['latest_catalogue_secondary'],'%Y%m%d').date().isoformat()}**.
Это ограничение каталога, а не ограничение прежней выборки из 15 наблюдений.
Для остальных трёх кадров над AOI также проверены все каталожные записи:
их последние secondary dates не позднее 25 марта 2026 года. Таким образом,
смена кадра в проверенной коллекции OPERA V1 не даёт покрытия летне-осенних окон.

{chr(10).join(comparison_lines)}

**Для интерфейса:** `{r['ui']['status']}`. Новые слои `up`/`east` не создаются.
Маска и доступность длинных рядов проверены численно; подтверждённая скорость
и вертикальное разложение не получены. Это ограничение результата, а не отсутствие
движения грунта.

**Разложение:** у двух самых длинных выбранных окон
**{r['decomposition']['shared_points_in_individually_longest_windows']}** общих координат.
Дополнительно проверены все **{r['decomposition']['long_window_combinations_with_90_day_overlap']}**
комбинаций связанных окон от 8 пар с временным пересечением минимум 90 дней:
максимум общих точек — **{r['decomposition']['maximum_shared_points_in_any_long_combination']}**.
Внешняя общая опора не подтверждена. Различающиеся даты сами по себе не запрещают
оценивать линейные скорости, но требуют обоснованной общей модели движения;
отсутствующие координаты или опору она не восстанавливает.

## Воспроизведение

```sh
.venv/bin/python -m scripts.download_mexico_remaining --inventory
# Только локальная Earthdata-авторизация; токен исключён из Git
.venv/bin/python -m scripts.download_mexico_remaining --workers 4
.venv/bin/python -m scripts.mexico_long_series
.venv/bin/python -m pytest scripts/test_mexico_long_series.py -q
# Обновить публичные независимые источники перед повторным расчётом:
.venv/bin/python -m scripts.mexico_long_series --refresh-gnss --refresh-opera-catalogue
```

Повторная загрузка проверяет кэш по ID и SHA-256 и возобновляется с недостающих
окон. Старые выборки не перезаписаны. Без всех гранул полный аудит останавливается.

- [Все числа, окна, источники гранул и входные SHA-256](../{OUTPUT}).
- [Квитанция загрузки](../data/analysis/mexico-gunw-download.json).
- [Каталог с исходным запросом CMR](../{M.CATALOGUE}).
- [Полный каталог OPERA с запросом и датой проверки](../data/evidence/mexico-opera-full-catalogue.json).
- [GNSS MMX1: решения, источник и контрольная сумма](../{GNSS}).
- [Дополнительные исходные выборки](../data/subsets/mexico-gunw-remaining/).
- [NASA/ASF: GUNW и неприменённые атмосферные поправки]({M.DOCS['gunw']}).
'''
    (M.ROOT/'docs/mexico-long-series.md').write_text(text)
    M.save(OUTPUT,r)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh-gnss',action='store_true')
    parser.add_argument('--refresh-opera-catalogue',action='store_true')
    args=parser.parse_args()
    if args.refresh_gnss:refresh_gnss()
    if args.refresh_opera_catalogue:refresh_opera_catalogue()
    r=calculate();write_outputs(r)
    print(json.dumps({d:{'pairs':v['count'],'zero_pairs':v['zero_quality_pairs'],
            'longest_10':v['longest_by_minimum_points']['10'],
            'reference':{k:x for k,x in v['reference_diagnosis'].items() if k in ['endpoint_reference_shift_range_cm','relative_rate_fit']}}
            for d,v in r['directions'].items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
