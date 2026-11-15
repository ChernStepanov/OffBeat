"""Воспроизводимая проверка GUNW/OPERA Мехико без публикации скорости.

python -m scripts.mexico_displacement [--refresh-catalogue]
Расчёт работает офлайн по исходным выборкам и проверяет их SHA-256.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = 'data/analysis/mexico-displacement-audit.json'
CATALOGUE = 'data/evidence/mexico-gunw-catalogue.json'
SPECS = {'ascending': (19, 11, 'Ascending', '2025-12-17'),
         'descending': (113, 79, 'Descending', '2026-01-05')}
DOCS = {
    'gunw': 'https://nisar-docs.asf.alaska.edu/gunw/',
    'opera': 'https://www.jpl.nasa.gov/go/opera/products/disp-product-suite/',
    'opera_usage': 'https://docs.asf.alaska.edu/datasets/disp_usage/',
    'sign': 'https://github.com/isce-framework/isce3/blob/develop/cxx/isce3/signal/Crossmul.cpp',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path, hashes):
    path = ROOT / path
    hashes[path.relative_to(ROOT).as_posix()] = digest(path)
    return json.loads(path.read_text())


def save(path, value):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def finite_list(a):
    return np.where(np.isfinite(a), a, None).tolist()


def summary(a):
    a = np.asarray(a); a = a[np.isfinite(a)]
    return {'count': int(a.size), 'p05_p50_p95': np.percentile(a, [5, 50, 95]).tolist() if a.size else None}


def quality_checks(a, coherence=.7):
    m = a['mask'].astype(np.uint32); sw = m & 255
    return {
        'finite_phase_ionosphere': np.isfinite(a['phase']) & np.isfinite(a['iono']),
        'coherence': np.isfinite(a['coherence']) & (a['coherence'] >= coherence) & (a['coherence'] <= 1),
        'component': (a['component'] > 0) & (a['component'] < 65535),
        'nonwater_subswaths': (sw < 100) & (sw // 10 > 0) & (sw % 10 > 0),
        'no_anomaly': (((m >> 8) & 65535) == 0) & ((m & 0xFE000000) == 0),
        'ionosphere_uncertainty': np.isfinite(a['iono_sd']) & (a['iono_sd'] >= 0) & (a['iono_sd'] <= 1),
    }


def quality(a, coherence=.7):
    return np.logical_and.reduce(list(quality_checks(a, coherence).values()))


def connected_intersection(pairs, coherence=.7):
    """Одна комбинация компонент по всем датам; метки между парами независимы."""
    common = np.logical_and.reduce([quality(p['arrays'], coherence) for p in pairs])
    if not common.any():
        return common, []
    signatures = np.stack([p['arrays']['component'][common] for p in pairs], axis=1)
    labels, counts = np.unique(signatures, axis=0, return_counts=True)
    signature = labels[np.argmax(counts)]
    for p, label in zip(pairs, signature):
        common &= p['arrays']['component'] == label
    return common, [int(x) for x in signature]


def chain(pairs, target, reference):
    """Диагностическая цепочка: фиксированные точки опоры и целей, без заполнения."""
    if not reference.any() or np.any(reference & ~target):
        raise ValueError('Опора отсутствует или не входит в общую маску')
    for i, p in enumerate(pairs):
        if i and pairs[i-1]['receipt']['secondary_date'] != p['receipt']['reference_date']:
            raise ValueError('Разрыв цепочки')
        a = p['arrays']
        if np.any(target & ~quality(a)):
            raise ValueError('Цель или опора не проходит маску на каждой дате')
        if len(np.unique(a['component'][target])) != 1:
            raise ValueError('Нельзя соединять независимые компоненты')
    delta, offsets = [], []
    for p in pairs:
        a, r = p['arrays'], p['receipt']
        factor = -299792458 / r['center_frequency_hz'] / (4*np.pi) * 100
        los = (a['phase'] - a['iono']) * factor
        offset = float(np.median(los[reference])); offsets.append(offset)
        delta.append(np.where(target, los-offset, np.nan))
    initial = np.where(target, 0., np.nan)
    return np.concatenate([initial[None], initial[None] + np.cumsum(delta, axis=0)]), offsets


def load_pairs(hashes, coordinates):
    result = {}
    for direction, (track, frame, word, _) in SPECS.items():
        pairs = []
        for path in sorted((ROOT/'data/subsets/mexico-gunw-series'/direction).glob('*.json')):
            r = read(path.relative_to(ROOT), hashes)
            p = ROOT/r['subset_path']
            if digest(p) != r['sha256']:
                raise ValueError('Нарушена контрольная сумма ' + p.name)
            hashes[r['subset_path']] = digest(p)
            with np.load(p) as f:
                a = {k: f[k] for k in f.files}
            ident = r['identification']
            if (ident['track'], ident['frame'], ident['direction'], ident['look_direction']) != (track, frame, word, 'Left'):
                raise ValueError('Несовместимая геометрия')
            if r['grid']['epsg'] != 32614 or r['grid']['spacing'] != [80., -80.]:
                raise ValueError('Неожиданная сетка')
            if any(a[k].shape != (32,32) for k in a) or not np.array_equal(np.stack([a['lat'].ravel(), a['lon'].ravel()], axis=1), coordinates):
                raise ValueError('Координаты выборок различаются')
            if not np.isfinite(r['center_frequency_hz']) or r['center_frequency_hz'] <= 0:
                raise ValueError('Неизвестная частота')
            if r['secondary_date'] <= r['reference_date']:
                raise ValueError('Обратные даты')
            if pairs and pairs[-1]['receipt']['secondary_date'] != r['reference_date']:
                raise ValueError('Непоследовательные сохранённые пары')
            if int(quality(a).sum()) != r['quality_valid_count']:
                raise ValueError('Число принятых точек не совпадает с квитанцией')
            pairs.append({'receipt': r, 'arrays': a, 'receipt_path': path.relative_to(ROOT).as_posix()})
        if not pairs:
            raise ValueError('Нет пар ' + direction)
        ids = [p['receipt']['source']['id'] for p in pairs]
        if len(set(ids)) != len(ids):
            raise ValueError('Повторные гранулы')
        result[direction] = pairs
    return result


def refresh_catalogue():
    """Публичная метаинформация; не требует Earthdata и не подменяет чтение масок."""
    import requests
    params = dict(short_name='NISAR_L2_GUNW_PROVISIONAL_V1',
                  bounding_box='-99.09,19.415,-99.065,19.44', page_size=2000, sort_key='start_date')
    response = requests.get('https://cmr.earthdata.nasa.gov/search/granules.json', params=params, timeout=90)
    response.raise_for_status()
    hits = int(response.headers['CMR-Hits'])
    entries = response.json()['feed']['entry']
    if hits != len(entries):
        raise ValueError('Нужна пагинация CMR')
    rows = []
    for g in entries:
        name = g['producer_granule_id']
        direction = next((d for d,(t,f,w,_) in SPECS.items()
                          if re.search(rf'_GUNW_\d+_{t:03}_{w[0]}_{f:03}_', name)), None)
        if direction is None:
            continue
        url = next((x['href'] for x in g.get('links', []) if x['href'].endswith('.h5')
                    and x['href'].startswith('https:') and x.get('rel', '').endswith('/data#')), None)
        rows.append({'id': name, 'concept_id': g['id'], 'direction': direction,
                     'start': g['time_start'], 'end': g['time_end'], 'url': url})
    save(CATALOGUE, {'checked_at': datetime.now(timezone.utc).isoformat(), 'query': response.url,
                     'cmr_hits': hits, 'granules': rows,
                     'scope': 'Только PROVISIONAL V1 и два выбранных track/frame; это не полный каталог VALIDATED и не проверка пикселей.'})


def opera_data(hashes, coordinates):
    op = read('data/mexico/opera-disp.json', hashes)
    if hashlib.sha256(json.dumps([tuple(p) for p in coordinates]).encode()).hexdigest() != op['points_sha256']:
        raise ValueError('OPERA: координаты не совпадают')
    dates, values = [], []
    for g in op['granules']:
        if g.get('reference_date') != op['reference_date'] or not g.get('url') or not g.get('concept_id') or '_F01088_VV_' not in g['id']:
            raise ValueError('OPERA: отсутствует происхождение или смешаны кадры/опоры')
        d = g['secondary_date']
        if d <= op['reference_date'] or (dates and d <= dates[-1]):
            raise ValueError('OPERA: повторные или обратные даты')
        row = np.asarray(g['values']['displacement'], dtype=float)
        if row.shape != (len(coordinates),) or np.isinf(row).any() or int(np.isfinite(row).sum()) != g['valid_samples']:
            raise ValueError('OPERA: неверные значения или размер')
        dates.append(d); values.append(row*100)
    if not dates:
        raise ValueError('Нет измерений OPERA')
    # Не добавляем искусственное наблюдение нуля на продуктовую опорную дату.
    return op, dates, np.array(values)


def nearest_interval(dates, ref, sec, max_days=3):
    indices, offsets = [], []
    for target in [ref, sec]:
        distances = [(date.fromisoformat(d)-date.fromisoformat(target)).days for d in dates]
        i = min(range(len(dates)), key=lambda j: (abs(distances[j]), dates[j]))
        indices.append(i); offsets.append(distances[i])
    accepted = max(abs(x) for x in offsets) <= max_days and indices[1] > indices[0]
    return indices, offsets, accepted


def calculate():
    hashes = {}
    site = read('data/mexico.json', hashes)
    coords = np.array([(p['lat'],p['lon']) for p in site['pixels']])
    all_pairs = load_pairs(hashes, coords)
    op, op_dates, op_values = opera_data(hashes, coords)
    selected = {d: [p for p in pairs if p['receipt']['reference_date'] >= SPECS[d][3]] for d,pairs in all_pairs.items()}
    masks = {}; result = {}
    for d, pairs in all_pairs.items():
        mask, labels = connected_intersection(selected[d]); masks[d] = mask
        rows = []
        for p in pairs:
            a, r = p['arrays'], p['receipt']; cumulative = np.ones((32,32), bool); waterfall = {}
            for name, check in quality_checks(a).items():
                cumulative &= check; waterfall[name] = int(cumulative.sum())
            rows.append({'reference_date': r['reference_date'], 'secondary_date': r['secondary_date'],
                         'source': r['source'], 'receipt': p['receipt_path'], 'valid': int(quality(a).sum()),
                         'mask_waterfall': waterfall,
                         'interpolated_ionosphere_among_valid': int((quality(a) & ((a['mask'] & (1 << 24)) != 0)).sum())})
        windows = []
        for start in range(len(pairs)):
            for end in range(start+3, len(pairs)+1):
                sub = pairs[start:end]; cm, _ = connected_intersection(sub)
                windows.append({'reference_date': sub[0]['receipt']['reference_date'],
                                'secondary_date': sub[-1]['receipt']['secondary_date'],
                                'pairs': len(sub), 'connected_points': int(cm.sum())})
        sel = selected[d]
        dates = [sel[0]['receipt']['reference_date']] + [p['receipt']['secondary_date'] for p in sel]
        result[d] = {'track': SPECS[d][0], 'frame': SPECS[d][1], 'sampled_pairs': rows,
                     'all_pairs_common_points': int(connected_intersection(pairs)[0].sum()),
                     'all_contiguous_windows_at_least_3_pairs': windows,
                     'selected_dates': dates, 'selected_pairs': len(sel),
                     'selected_span_days': (date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days,
                     'selected_connected_points': int(mask.sum()), 'component_signature': labels,
                     'coherence_sensitivity': {str(c): int(connected_intersection(sel,c)[0].sum()) for c in [.6,.7,.8]},
                     'pairs_with_los_enu': sum('los_enu' in p['arrays'] for p in sel),
                     'pairs_with_flattening_receipt': sum('flattening' in p['receipt']['grid'] for p in sel)}
    shared = masks['ascending'] & masks['descending']
    # Одна и та же фиксированная пространственная опора для обоих радаров и всех дат.
    reference = shared & np.isfinite(op_values).all(axis=0).reshape(32,32)
    rr, cc = np.indices((32,32))
    refs = {'shared': reference}
    sector_counts = {}
    for name, sector in {'NW':(rr<16)&(cc<16), 'NE':(rr<16)&(cc>=16),
                         'SW':(rr>=16)&(cc<16), 'SE':(rr>=16)&(cc>=16)}.items():
        candidate = reference & sector; sector_counts[name] = int(candidate.sum())
        if candidate.sum() >= 3:
            refs[name] = candidate
    for d, sel in selected.items():
        chains, offsets = {}, {}
        for name, ref in refs.items():
            chains[name], offsets[name] = chain(sel, masks[d], ref)
        baseline = chains['shared']
        shifts = {name: [float(np.median((v[t]-baseline[t])[masks[d]])) for t in range(len(v))]
                  for name,v in chains.items()}
        result[d].update({'diagnostic_los_cm': finite_list(baseline.reshape(len(baseline),-1)),
                          'reference_offsets_cm_each_pair': offsets,
                          'reference_sensitivity_shift_cm': shifts,
                          'end_displacement_cm': summary(baseline[-1]),
                          'endpoint_reference_shift_range_cm': float(np.ptp([s[-1] for s in shifts.values()])),
                          'reference_stability': 'не установлена; малый разброс относительных опор не доказывает неподвижность'})
        comparisons = []
        for j,p in enumerate(sel):
            r = p['receipt']; indices, offsets_days, usable = nearest_interval(op_dates, r['reference_date'],r['secondary_date'])
            row = {'nisar_dates': [r['reference_date'],r['secondary_date']],
                   'opera_dates': [op_dates[i] for i in indices], 'offset_days': offsets_days,
                   'within_3_days': usable,
                   'physical_agreement': 'не оценивается: отсутствуют векторы LOS и проверка компонент OPERA'}
            if usable:
                v = (op_values[indices[1]]-op_values[indices[0]]).reshape(32,32)
                v -= np.median(v[reference])
                good = masks[d] & np.isfinite(v)
                delta = baseline[j+1]-baseline[j]
                row.update({'common_points': int(good.sum()), 'nisar_delta_cm': summary(delta[good]),
                            'opera_delta_cm': summary(v[good]),
                            'opera_granule_ids': [op['granules'][i]['id'] for i in indices]})
            comparisons.append(row)
        result[d]['opera_interval_check'] = comparisons
    gnss = read('data/analysis/mexico-mmx1-gnss.json', hashes)
    raw_gnss = ROOT/gnss['subset_path']
    if digest(raw_gnss) != gnss['subset_sha256']:
        raise ValueError('GNSS: нарушена контрольная сумма')
    hashes[gnss['subset_path']] = digest(raw_gnss)
    i = gnss['nearest_nisar_sample']['index']
    station = {'station': gnss['station'], 'distance_m': gnss['nearest_nisar_sample']['distance_m'],
               'source_url': gnss['source_url'], 'selected_pairs_accepted': {
                   d: int(sum(quality(p['arrays']).ravel()[i] for p in sel)) for d,sel in selected.items()},
               'usable_as_nisar_chain_anchor': bool(reference.ravel()[i]),
               'stable_reference': False}
    catalogue = read(CATALOGUE, hashes)
    for d in result:
        result[d]['catalogue_granules'] = sum(g['direction']==d for g in catalogue['granules'])
        result[d]['catalogue_not_sampled'] = len({g['id'] for g in catalogue['granules'] if g['direction']==d}
                                                   - {p['receipt']['source']['id'] for p in all_pairs[d]})
    joint_start = max(v['selected_dates'][0] for v in result.values())
    joint_end = min(v['selected_dates'][-1] for v in result.values())
    exact = len(set(result['ascending']['selected_dates']) & set(result['descending']['selected_dates']))
    return {'schema_version': 1, 'kind': 'diagnostic_relative_los_not_velocity', 'method': 'scripts/mexico_displacement.py',
            'input_sha256': hashes, 'sources': DOCS, 'sample_count': len(coords),
            'implementation_sha256': digest(Path(__file__)),
            'software': {'python': sys.version.split()[0], 'numpy': np.__version__},
            'selection': 'Заранее сохранённые в mexico-gunw-postgap-quality отрезки; дополнительно показаны все окна от трёх пар. Порог 0.7 не изменялся.',
            'directions': result, 'shared_connected_points': int(shared.sum()),
            'reference': {'indices': np.flatnonzero(reference).tolist(), 'count': int(reference.sum()),
                          'sector_counts': sector_counts, 'minimum_sector_samples': 3,
                          'stability_verified': False, 'method': 'Фиксированные точки из пересечения обоих направлений и всех 15 маскированных OPERA дат; медиана отдельно в каждой паре. Квадранты определены по середине AOI, без отбора по смещению.'},
            'gnss': station, 'opera': {'reference_date': op['reference_date'], 'dates': op_dates,
                'accepted_counts': [g['valid_samples'] for g in op['granules']],
                'all_dates_finite_points': int(np.isfinite(op_values).all(axis=0).sum()),
                'granules': [{k:g[k] for k in ['id','concept_id','url','reference_date','secondary_date']} for g in op['granules']],
                'raw_masks_components_geometry_saved': False,
                'quantity': 'displacement, без пространственного фильтра short_wavelength_displacement',
                'independent_validation': False},
            'decomposition': {'available': False, 'overlap_days': (date.fromisoformat(joint_end)-date.fromisoformat(joint_start)).days,
                'overlap_dates': [joint_start,joint_end], 'exact_common_epochs': exact,
                'common_points': int(shared.sum()), 'los_enu_available': False,
                'reason': 'Нет векторов LOS, единой подтверждённой опоры, общих эпох и поправок атмосферы; допущение N=0 отдельно не проверено.'},
            'ui': {'status': 'insufficient_for_velocity', 'velocity_available': False, 'vertical_east_available': False,
                'message_ru': f"GUNW: диагностические относительные смещения за {result['ascending']['selected_span_days']}/{result['descending']['selected_span_days']} дней; общих точек {int(shared.sum())}/{len(coords)}. Стабильность опоры и согласие с OPERA не подтверждены. Подтверждённая скорость и вертикальное разложение недоступны.",
                'report': 'docs/mexico-displacement.md'},
            'limitations': ['Нет годового ряда: длинные сохранённые цепочки имеют нулевое пересечение строгих масок.',
                'Ноль начальной эпохи — соглашение, не отдельное измерение. Одиночная пара не пересчитывается в см/год.',
                'В новых квитанциях нет подтверждения flattening и векторов LOS; преобразование фазы диагностическое, по прежнему знаку -c/(4πf). Знак не выбирался по ожидаемому проседанию.',
                'Вычтена ионосфера. Тропосфера и приливы не исправлены; временная ковариация ошибок неизвестна.',
                'Принятые образцы с битом 24 сохранены и посчитаны; интерполированная ионосфера увеличивает ограничения.',
                'Чувствительность к опоре — не доверительный интервал. Общий дрейф всей AOI относительно внешней системы отсчёта не определяется.',
                'OPERA измерен независимо Sentinel-1, но raw quality/component/geometry не сохранены: повторная проверка удалённых масок невозможна офлайн.',
                'Сдвиг дат до трёх дней — только соседний интервал; LOS разных геометрий не являются общей физической величиной. Числа рядом не подтверждают согласие.',
                'Проверены только локальные 16 пар и каталог PROVISIONAL V1; вывод не распространяется на непрочитанные/VALIDATED гранулы.']}


def plots(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter
    target = ROOT/'docs/figures/mexico-displacement'; target.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(2,1, figsize=(11,7), layout='constrained')
    for ax,(d,r) in zip(axes, report['directions'].items()):
        rows = r['sampled_pairs']; counts = [p['valid'] for p in rows]
        ax.bar(range(len(rows)), counts, color='#206695' if d=='ascending' else '#b15b22')
        ax.set_xticks(range(len(rows)), [p['reference_date'] for p in rows], rotation=20)
        for j,v in enumerate(counts): ax.text(j,v+13,str(v),ha='center')
        ax.set_ylim(0,550); ax.set_ylabel('Точек из 1024'); ax.set_title(f"{d}: маски каждой пары; сквозь все 8 пар — {r['all_pairs_common_points']}")
    fig.savefig(target/'quality.png',dpi=150); plt.close(fig)
    fig, axes = plt.subplots(2,2, figsize=(12,7), layout='constrained')
    for col,(d,r) in enumerate(report['directions'].items()):
        t = [date.fromisoformat(x) for x in r['selected_dates']]
        arr = np.asarray(r['diagnostic_los_cm'],dtype=float)
        q = np.nanpercentile(arr,[5,50,95],axis=1)
        ax = axes[0,col]; ax.fill_between(t,q[0],q[2],alpha=.2,label='5–95% точек (не ошибка)')
        ax.plot(t,q[1],'o-',label='Медиана'); ax.axhline(0,color='grey',lw=.7)
        ax.set_title(f"{d}, {r['selected_connected_points']}/1024 точек"); ax.set_ylabel('Диагностическое LOS, см'); ax.legend(fontsize=8)
        ax = axes[1,col]
        for name,shift in r['reference_sensitivity_shift_cm'].items(): ax.plot(t,shift,'o-',label=name)
        ax.set_ylabel('Сдвиг при смене опоры, см'); ax.legend(fontsize=8); ax.set_title('Стабильность опоры не подтверждена')
        for ax in axes[:,col]:
            ax.set_xticks(t); ax.xaxis.set_major_formatter(DateFormatter('%d.%m')); ax.tick_params(axis='x',rotation=25)
    fig.suptitle('Фиксированная пространственная опора; атмосферные остатки сохранены. Это не скорость.')
    fig.savefig(target/'chains-reference.png',dpi=150); plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(11,7),layout='constrained')
    for ax,(d,r) in zip(axes,report['directions'].items()):
        rows=r['opera_interval_check']; labels=[]
        for j,row in enumerate(rows):
            labels.append(' →\n'.join(row['nisar_dates']))
            if not row['within_3_days']:
                ax.text(j,0,'Нет близких дат',ha='center',va='bottom',fontsize=9); continue
            for key,dx,color,marker,label in [('nisar_delta_cm',-.1,'#206695','o','NISAR'),('opera_delta_cm',.1,'#b15b22','s','OPERA')]:
                q=row[key]['p05_p50_p95']
                ax.vlines(j+dx,q[0],q[2],color=color,lw=2)
                ax.plot(j+dx,q[1],marker,color=color,label=label if j==next(k for k,x in enumerate(rows) if x['within_3_days']) else None)
        ax.set_xlim(-.5,len(rows)-.5); ax.set_xticks(range(len(rows)),labels)
        ax.axhline(0,color='grey',lw=.7)
        ax.set_title(d+': медиана и 5–95% общих точек'); ax.set_ylabel('Относительный LOS, см'); ax.legend()
    fig.suptitle('Соседние интервалы NISAR / OPERA: разные LOS, не проверка физического согласия')
    fig.savefig(target/'opera-intervals.png',dpi=150); plt.close(fig)


def write_report(r):
    a,d = [r['directions'][k] for k in ['ascending','descending']]
    comparisons = []
    for direction,v in r['directions'].items():
        for p in v['opera_interval_check']:
            if p['within_3_days']:
                n,o = [p[k]['p05_p50_p95'] for k in ['nisar_delta_cm','opera_delta_cm']]
                comparisons.append(f"| {direction} | {' → '.join(p['nisar_dates'])} | {' → '.join(p['opera_dates'])} | {p['common_points']} | {n[1]:.3f} | {o[1]:.3f} |")
    text = f'''# Мехико: доступность временного ряда смещений (#16, #36)

Это исходный срез первых 16 пар. Результат последующей догрузки всех 54 гранул
приведён [в полном расчёте](mexico-long-series.md); ограничения ниже относятся
к исходному срезу, а не к состоянию после догрузки.

**Вывод:** сохранённых измерений достаточно для коротких диагностических рядов
относительного LOS, но недостаточно для подтверждённой скорости и разложения на
вертикаль/восток. Стабильная опорная область не установлена. OPERA даёт независимые
измерения, однако физическое согласие с NISAR по этим выборкам подтвердить нельзя.

## Покрытие и маски

| Показатель | 019A/011 | 113D/079 |
|---|---:|---:|
| Гранулы в сохранённом свежем запросе PROVISIONAL V1 | {a['catalogue_granules']} | {d['catalogue_granules']} |
| Прочитанные пары, с исходными слоями качества и SHA-256 | 8 | 8 |
| Каталожные гранулы без локальной выборки | {a['catalogue_not_sampled']} | {d['catalogue_not_sampled']} |
| Точки, прошедшие все восемь пар | {a['all_pairs_common_points']} | {d['all_pairs_common_points']} |
| Выбранный отрезок | {' → '.join([a['selected_dates'][0],a['selected_dates'][-1]])} | {' → '.join([d['selected_dates'][0],d['selected_dates'][-1]])} |
| Последовательных пар / дней | {a['selected_pairs']} / {a['selected_span_days']} | {d['selected_pairs']} / {d['selected_span_days']} |
| Точек в одной комбинации компонент во всех выбранных парах | {a['selected_connected_points']}/1024 (26,86%) | {d['selected_connected_points']}/1024 (6,64%) |
| При пороге coherence 0,6 / 0,7 / 0,8 | {' / '.join(str(x) for x in a['coherence_sensitivity'].values())} | {' / '.join(str(x) for x in d['coherence_sensitivity'].values())} |

Общих координат **{r['shared_connected_points']}/1024 (3,81%)**; временное пересечение
**{r['decomposition']['overlap_days']} дней**, {' → '.join(r['decomposition']['overlap_dates'])}.
Точных общих эпох: **{r['decomposition']['exact_common_epochs']}**. Число точек — число
разреженных мест выборки, не число независимых наблюдений и не площадь.

![Прохождение масок по каждой паре](figures/mexico-displacement/quality.png)

Сохранены результаты для **всех 42 последовательных окон от трёх пар** (21 на
направление), включая пустые. Выбранные отрезки соответствуют прежнему
`mexico-gunw-postgap-quality.json`, а не максимуму смещения. Анализ чувствительности
порога не меняет основной порог 0,7 и не означает принятие более слабой маски.
Каталог ограничен PROVISIONAL V1: непрочитанные и VALIDATED продукты не признаны
непригодными. Отсутствие длинного ряда установлено для сохранённых выборок.

Маска требует конечных phase/ionosphere, coherence в [0,7; 1], component в
1…65534, невода и валидных подсвотов в младшем байте, отсутствия anomaly bits
8…23 и 25…31, ionosphere uncertainty в [0; 1] рад. Бит 24 интерполированной
ионосферы допускается и подсчитан отдельно. Каскад исключений по каждой паре
сохранён в JSON. Компонентные метки независимы между парами: используется
одна наиболее многочисленная **комбинация** меток, а не равенство номера между датами.

## Опора и диагностическое смещение

Из 39 общих координат **{r['reference']['count']}** также имеют конечное OPERA
на всех датах. Эти фиксированные координаты используются для медианной опоры
каждой пары. Контрольные квадранты AOI: NW 0, NE 3, SW 5, SE 30 точек;
NW не используется. Отбор по величине смещения не выполнялся. Это технические
области для проверки чувствительности, а не доказанно стабильный грунт.

Вычитается ионосферная фаза, затем пространственная медиана опоры. Преобразование:
`LOS_cm = -(phase-ionosphere) × 299792458/(4πf) × 100`; положительное направление
— к спутнику, по прежней конвенции проекта. Тропосфера и приливы не удалены.
Данные новых квитанций не содержат подтверждения flattening; поэтому эти цепочки
помечены диагностическими. Знак не подгоняется под ожидаемое проседание.
Нулевая эпоха — соглашение; наблюдения через пробелы не соединяются.

![Диагностические цепочки и чувствительность к опоре](figures/mexico-displacement/chains-reference.png)

Диапазон сдвига конечного результата при выборе трёх допустимых квадрантов и
общей опоры: **{a['endpoint_reference_shift_range_cm']:.3f} см ascending** и
**{d['endpoint_reference_shift_range_cm']:.3f} см descending**. Это не доверительный
интервал: общий дрейф всей AOI и пространственно коррелированная атмосфера могут
сохраниться при любой из этих опор. Малый относительный разброс не подтверждает
неподвижность. Полосы 5–95% на графике показывают пространственный разброс точек,
не точность оценки.

Станция MMX1 расположена в {r['gnss']['distance_m']} м от ближайшей точки, но она
проходит только **2/4 ascending и 0/3 descending** масок. Использовать эту точку
для привязки цепочки нельзя. Сам GNSS также не является неподвижной опорой.
Отдельно показанная ранее GNSS-привязка OPERA остаётся модельной оценкой с
допущениями, а не независимой проверкой NISAR.

## Независимый OPERA DISP-S1

Проверены координатный fingerprint, общий frame F01088, опорная дата
{r['opera']['reference_date']}, строгий порядок **15 наблюдений** за
{r['opera']['dates'][0]} → {r['opera']['dates'][-1]}, размерность, конечность и
число принятых значений **1018–1021/1024**; на всех датах доступны
**{r['opera']['all_dates_finite_points']}** координат. Искусственный ноль на
опорную дату не добавлен. Речь идёт о сохранённых после `recommended_mask=1`
значениях: исходные recommended mask, connected components и геометрия OPERA
не сохранены, поэтому удалённые маски здесь повторно не проверялись.

Сверка использует **нефильтрованный `displacement`**, а не локально
фильтрованный `short_wavelength_displacement` из прежнего UI. У всех продуктов
сохранены ID/CMR ID/URL. К каждой NISAR-дате выбрана ближайшая реальная OPERA-дата
с допуском не более трёх суток, без интерполяции и экстраполяции. Начало первой
ascending пары отстоит на 14 дней и отклоняется; остальные ascending интервалы
сдвинуты на +2 дня, descending на +1 день.

| Направление | NISAR интервал | OPERA интервал | Общих точек | Медиана NISAR, см | Медиана OPERA, см |
|---|---|---|---:|---:|---:|
{chr(10).join(comparisons)}

![Соседние интервалы NISAR и OPERA](figures/mexico-displacement/opera-intervals.png)

Это **описательное сопоставление двух разных LOS**, после одинаковой
пространственной привязки. Медианы около нуля отчасти заданы самой опорой.
Без проекции в общую геометрию, контроля компонент и атмосферных поправок
численное сходство не является валидацией; RMSE согласия и «точность» не заявляются.
Исходная рекомендация OPERA выбирать высококачественные пиксели не доказывает
геологическую стабильность продуктовой опоры.

## Что показывать в интерфейсе

Состояние в JSON: `insufficient_for_velocity`, `velocity_available=false`,
`vertical_east_available=false`. Показывать исходную одиночную пару в сантиметрах
с её собственными датами; рядом — ограничения ряда и ссылку на этот расчёт.
Диагностические цепочки доступны в отчёте. Не выдавать 48/36-дневное относительное
смещение за годовую скорость. Слои NISAR `up`/`east` не создаются.

Для скорости нужны более длинные связанные выборки, документированная
стабильная или измеренная внешняя опора, подтверждение обработки фазы, поправки
атмосферы и оценка временной ковариации ошибок. Для разложения дополнительно
нужны LOS ENU векторы обоих направлений, согласованные интервалы и обоснование
допущения северного движения. В сохранённых парах LOS векторов **0/7**.

## Воспроизведение и источники

```sh
.venv/bin/python -m pip install -r scripts/requirements.txt
.venv/bin/python -m scripts.mexico_displacement
.venv/bin/python -m pytest scripts/test_mexico_displacement.py -q
# Необязательно: обновить только публичный каталог (изменит его дату и SHA-256)
.venv/bin/python -m scripts.mexico_displacement --refresh-catalogue
```

Расчёт офлайн заново проверяет SHA-256 всех NPZ и координаты относительно
`data/mexico.json`, читает исходные quality layers, пересчитывает маски и цепочки,
записывает JSON и три PNG. Изменение входов меняет `input_sha256`; несовпадение
NPZ с исходной квитанцией останавливает расчёт. Скрипт не изменяет исходные
измерения. Для повторной выгрузки оригиналов нужны Earthdata Login и скрипты
`inspect_mexico_gunw_series.py` / `inspect_opera_disp.py`. Доступа Earthdata в
этом запуске не использовалось; новые измерения из непрочитанных гранул не заявлены.

- [Числа, цепочки, маски, все источники гранул и входные SHA-256](../data/analysis/mexico-displacement-audit.json).
- [Свежий запрос CMR, дата проверки и 54 гранулы](../data/evidence/mexico-gunw-catalogue.json).
- [Исходные GUNW NPZ и квитанции](../data/subsets/mexico-gunw-series/).
- [Исходная выборка OPERA](../data/mexico/opera-disp.json).
- [NASA/ASF: GUNW, единицы и неприменённые поправки]({DOCS['gunw']}).
- [NASA/JPL: спецификации OPERA DISP-S1]({DOCS['opera']}).
- [ASF: использование OPERA и маски]({DOCS['opera_usage']}).
- [ISCE3 Crossmul: конвенция фазы]({DOCS['sign']}).
'''
    (ROOT/'docs/mexico-displacement.md').write_text(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-catalogue',action='store_true')
    args=parser.parse_args()
    if args.refresh_catalogue: refresh_catalogue()
    report=calculate(); save(OUT,report); plots(report); write_report(report)
    print(json.dumps({'shared':report['shared_connected_points'], 'reference_count':report['reference']['count'],
                      'directions':{d:{k:r[k] for k in ['catalogue_granules','catalogue_not_sampled','selected_span_days','selected_connected_points','endpoint_reference_shift_range_cm']} for d,r in report['directions'].items()},
                      'ui':report['ui']},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
