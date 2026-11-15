"""Statistical findings across all prepared NISAR sites, from measured values only.

Each finding states how strong it is and how it was tested. Nothing is interpolated,
filled or simulated: missing measurements stay missing and reduce the sample size.

Run from the repository root: .venv/bin/python -m scripts.findings
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
SITES = ['mexico', 'amazon', 'venezuela', 'delhi', 'tokyo', 'khimki', 'nairobi', 'sydney']
CLASSES = {10: ('tree cover', 'лес'), 20: ('shrubland', 'кустарник'), 30: ('grassland', 'луга'), 40: ('cropland', 'пашня'),
           50: ('built-up', 'застройка'), 60: ('bare ground', 'голая земля'), 80: ('water', 'вода')}
OFFBEAT = 2.5          # |z| the map calls off-beat
MIN_CLASS = 20         # samples a class needs before its statistics are reported
PERMUTATIONS = 4999
REPEAT_DAYS = 12       # NISAR repeat interval; longer gaps are not used for the noise floor
GAUSS_INSIDE_2 = float(stats.norm.cdf(2) - stats.norm.cdf(-2))
GAUSS_OFFBEAT = float(2 * stats.norm.sf(OFFBEAT))


def series(pixels, key):
    return np.array([[np.nan if v is None else v for v in p[key]] for p in pixels], dtype=float)


def r(value, digits=2):
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def joins(mask):
    """Rook-adjacent pairs where both samples are flagged."""
    return int((mask[:, 1:] & mask[:, :-1]).sum() + (mask[1:, :] & mask[:-1, :]).sum())


def clustering(z, n, rng):
    grid = z.reshape(n, n)
    valid = np.isfinite(grid)
    flagged = valid & (np.abs(grid) > OFFBEAT)
    observed = joins(flagged)
    labels = flagged[valid]
    null = np.empty(PERMUTATIONS, dtype=int)
    shuffled = np.zeros_like(flagged)
    for k in range(PERMUTATIONS):
        shuffled[valid] = rng.permutation(labels)
        null[k] = joins(shuffled)
    p = (1 + int((null >= observed).sum())) / (1 + PERMUTATIONS)
    return {'flagged': int(flagged.sum()), 'valid': int(valid.sum()), 'adjacent_pairs': observed,
            'expected_pairs': r(null.mean(), 1), 'p': r(p, 4), 'permutations': PERMUTATIONS,
            'test': 'rook join count of |z| > 2.5 samples vs random relabelling of valid samples'}


def persistence(zhv):
    flagged = np.abs(zhv) > OFFBEAT
    valid = np.isfinite(zhv)
    both_valid = valid[:, :-1] & valid[:, 1:]
    first = (flagged[:, :-1] & both_valid).sum()
    if first == 0:
        return None
    again = (flagged[:, :-1] & flagged[:, 1:] & both_valid).sum() / first
    base = flagged[:, 1:][both_valid].mean()
    return {'flag_again': r(again, 3), 'base_rate': r(base, 3), 'lift': r(again / base, 1),
            'ever_flagged': int(flagged.any(1).sum()), 'flagged_half_or_more': int((flagged.sum(1) >= zhv.shape[1] / 2).sum())}


def repeat_pairs(dates):
    days = [date.fromisoformat(d) for d in dates]
    return [i for i in range(len(days) - 1) if (days[i + 1] - days[i]).days <= REPEAT_DAYS]


def noise_floor(hv, cover, dates):
    pairs = repeat_pairs(dates)
    if not pairs:
        return {}
    out = {}
    for c in sorted(set(cover)):
        m = cover == c
        if m.sum() < MIN_CLASS or c not in CLASSES:
            continue
        d = np.abs(hv[m][:, [i + 1 for i in pairs]] - hv[m][:, pairs]).ravel()
        d = d[np.isfinite(d)]
        if len(d):
            out[str(c)] = {'samples': int(m.sum()), 'differences': int(len(d)), 'median_db': r(np.median(d)), 'p90_db': r(np.percentile(d, 90))}
    return out


def common_mode(hv, cover, dates, threshold=2.0):
    """Dates where every reported land-cover class shifts the same way by >= threshold dB."""
    classes = [c for c in sorted(set(cover)) if (cover == c).sum() >= MIN_CLASS and c in CLASSES]
    shifts = []
    for i in range(len(dates) - 1):
        moves = {}
        for c in classes:
            d = hv[cover == c, i + 1] - hv[cover == c, i]
            d = d[np.isfinite(d)]
            if len(d) >= MIN_CLASS:
                moves[str(c)] = float(np.median(d))
        values = list(moves.values())
        if len(values) >= 2 and all(abs(v) >= threshold for v in values) and (all(v > 0 for v in values) or all(v < 0 for v in values)):
            shifts.append({'from': dates[i], 'to': dates[i + 1], 'median_shift_db': {k: r(v) for k, v in moves.items()}})
    return shifts


def trends(pixels, dates, alpha=0.05):
    """Mann-Kendall-style test (Kendall tau vs time) on peer z, Benjamini-Hochberg across samples and channels."""
    t = np.array([date.fromisoformat(d).toordinal() for d in dates], dtype=float)
    tests = []
    for channel in ['hv', 'hh']:
        z = series(pixels, f'z_{channel}')
        own = series(pixels, channel)
        med = np.array([[np.nan if v is None else v for v in p['peer'][f'{channel}_med']] for p in pixels], dtype=float)
        for i in range(len(pixels)):
            m = np.isfinite(z[i]) & np.isfinite(own[i]) & np.isfinite(med[i])
            if m.sum() < max(10, int(0.7 * len(dates))):
                continue
            _, p = stats.kendalltau(t[m], z[i][m])
            slope = stats.theilslopes(own[i][m] - med[i][m], t[m] / 365.25)[0]
            tests.append((i, channel, p, slope))
    if not tests:
        return None
    q = stats.false_discovery_control([x[2] for x in tests])
    hits = [{'index': i, 'id': pixels[i]['id'], 'channel': ch, 'cover': pixels[i]['cover'], 'q': r(qv, 4),
             'slope_db_per_year': r(s, 1)} for (i, ch, _, s), qv in zip(tests, q) if qv < alpha]
    hits.sort(key=lambda h: -abs(h['slope_db_per_year']))
    samples = sorted({h['index'] for h in hits})
    return {'tests': len(tests), 'alpha': alpha, 'significant_tests': len(hits), 'samples': len(samples),
            'brightening': sum(h['slope_db_per_year'] > 0 for h in hits), 'darkening': sum(h['slope_db_per_year'] < 0 for h in hits),
            'expected_false_at_most': int(np.ceil(alpha * len(hits))), 'strongest': hits[:12],
            'test': 'Kendall tau of peer z vs time per sample and channel; Benjamini-Hochberg FDR; Theil-Sen slope of own minus peer median'}


def quality(hh, hv, cover, coherence, dates):
    pairs = repeat_pairs(dates)
    swing = np.abs(hv[:, [i + 1 for i in pairs]] - hv[:, pairs]) if pairs else np.array([np.nan])
    stats_ = {'median_hh_db': r(np.nanmedian(hh)), 'median_hv_db': r(np.nanmedian(hv)),
              'hv_above_hh_share': r(np.nanmean((hv > hh)[np.isfinite(hv) & np.isfinite(hh)]), 3),
              'repeat_swing_median_db': r(np.nanmedian(swing)),
              'median_coherence': r(np.nanmedian(coherence)) if np.isfinite(coherence).any() else None}
    reasons = []
    # L-band cross-pol backscatter of land surfaces sits well below 0 dB and below co-pol.
    if stats_['median_hv_db'] is not None and stats_['median_hv_db'] > -5:
        reasons.append(['median HV is above -5 dB, brighter than land surfaces return at L band', 'медиана HV выше -5 дБ: ярче, чем возвращает суша в L-диапазоне'])
    if stats_['hv_above_hh_share'] is not None and stats_['hv_above_hh_share'] > 0.5:
        reasons.append(['HV exceeds HH for most samples, the reverse of normal scattering', 'у большинства точек HV больше HH, обратно нормальному рассеянию'])
    if stats_['repeat_swing_median_db'] is not None and stats_['repeat_swing_median_db'] > 6:
        reasons.append(['typical 12-day HV swing is above 6 dB', 'типичный скачок HV за 12 дней больше 6 дБ'])
    return {**stats_, 'plausible': not reasons, 'reasons': reasons}


def analyse(site, rng):
    px = site['pixels']; n = site['grid']['n']; dates = site['dates']
    hh, hv, zhv = series(px, 'hh'), series(px, 'hv'), series(px, 'z_hv')
    zhh = series(px, 'z_hh')
    cover = np.array([p['cover'] or 0 for p in px])
    coherence = np.array([np.nan if p.get('coherence') is None else p['coherence'] for p in px], dtype=float)
    z = np.array([np.nan if p['z'] is None else p['z'] for p in px], dtype=float)
    peer_z = np.concatenate([zhv[np.isfinite(zhv)], zhh[np.isfinite(zhh)]])
    by_class = {}
    for c in sorted(set(cover)):
        m = cover == c
        if m.sum() < MIN_CLASS or c not in CLASSES:
            continue
        by_class[str(c)] = {'samples': int(m.sum()), 'hh_db': r(np.nanmedian(hh[m])), 'hv_db': r(np.nanmedian(hv[m])),
                            'coherence': r(np.nanmedian(coherence[m])) if np.isfinite(coherence[m]).any() else None}
    return {
        'id': site['id'], 'name': site['name'], 'dates': len(dates), 'first': dates[0], 'last': dates[-1],
        'quality': quality(hh, hv, cover, coherence, dates),
        'calibration': {'inside_2': r(np.mean(np.abs(peer_z) <= 2), 3), 'measurements': int(len(peer_z)), 'gaussian_inside_2': r(GAUSS_INSIDE_2, 3)},
        'offbeat': {'share': r(np.mean(np.abs(z[np.isfinite(z)]) > OFFBEAT), 3), 'gaussian_share': r(GAUSS_OFFBEAT, 4)},
        'clustering': clustering(z, n, rng),
        'persistence': persistence(zhv) if len(dates) >= 3 else None,
        'noise_floor': noise_floor(hv, cover, dates),
        'common_mode': common_mode(hv, cover, dates),
        'trends': trends(px, dates) if len(dates) >= 10 else None,
        'classes': by_class,
    }


def names(sites, ids):
    return ', '.join(sites[i]['name'].split(',')[0] for i in ids)


def build_findings(sites):
    """Plain-language conclusions. Strength: strong, suggestive, none (tested, not supported) or issue (data problem)."""
    ok = [k for k, s in sites.items() if s['quality']['plausible']]
    bad = [k for k, s in sites.items() if not s['quality']['plausible']]
    out = []

    for k in bad:
        q = sites[k]['quality']
        out.append({'id': f'quality-{k}', 'strength': 'issue', 'site': k,
            'en': f"{sites[k]['name']}: the radar values fail physical plausibility checks, so its off-beat samples are not findings.",
            'ru': f"{sites[k]['name']}: значения радара не проходят проверку физической правдоподобности, поэтому выбросы здесь не находки.",
            'how_en': f"Median HH {q['median_hh_db']} dB, HV {q['median_hv_db']} dB, HV above HH in {round(100*q['hv_above_hh_share'])}% of samples, typical 12-day swing {q['repeat_swing_median_db']} dB, coherence {q['median_coherence']}. " + '; '.join(x[0] for x in q['reasons']).capitalize() + '. This pattern is consistent with radio-frequency interference or a faulty provisional product; the cause is not established.',
            'how_ru': f"Медиана HH {q['median_hh_db']} дБ, HV {q['median_hv_db']} дБ, HV больше HH у {round(100*q['hv_above_hh_share'])}% точек, типичный скачок за 12 дней {q['repeat_swing_median_db']} дБ, когерентность {q['median_coherence']}. " + '; '.join(x[1] for x in q['reasons']).capitalize() + '. Картина согласуется с радиопомехами или дефектом предварительного продукта; причина не установлена.'})

    inside = [sites[k]['calibration']['inside_2'] for k in ok]
    out.append({'id': 'calibration', 'strength': 'strong', 'site': None,
        'en': f"The neighbour band is honest: {round(100*min(inside))}-{round(100*max(inside))}% of measurements fall inside it, near the 95% it is designed for.",
        'ru': f"Полоса соседей работает честно: в неё попадает {round(100*min(inside))}-{round(100*max(inside))}% измерений, близко к расчётным 95%.",
        'how_en': f"Share of per-date peer z-scores with |z| <= 2 across {len(ok)} sites with plausible data ({sum(sites[k]['calibration']['measurements'] for k in ok):,} HH and HV measurements). A Gaussian gives {round(100*GAUSS_INSIDE_2, 1)}%. Off-beat (|z| > 2.5) shares are {round(100*min(sites[k]['offbeat']['share'] for k in ok), 1)}-{round(100*max(sites[k]['offbeat']['share'] for k in ok), 1)}%, above the Gaussian {round(100*GAUSS_OFFBEAT, 1)}%: radar tails are heavier, so a single |z| > 2.5 is common.",
        'how_ru': f"Доля z-оценок по датам с |z| <= 2 на {len(ok)} участках с правдоподобными данными ({sum(sites[k]['calibration']['measurements'] for k in ok):,} измерений HH и HV). Для нормального распределения {round(100*GAUSS_INSIDE_2, 1)}%. Доля выбросов (|z| > 2.5) {round(100*min(sites[k]['offbeat']['share'] for k in ok), 1)}-{round(100*max(sites[k]['offbeat']['share'] for k in ok), 1)}%, выше нормальных {round(100*GAUSS_OFFBEAT, 1)}%: хвосты у радара тяжелее, и одиночный |z| > 2.5 встречается часто."})

    clustered = sorted((k for k in ok if sites[k]['clustering']['p'] < 0.05), key=lambda k: sites[k]['clustering']['p'])
    scattered = [k for k in ok if sites[k]['clustering']['p'] >= 0.05]
    for k in clustered:
        c = sites[k]['clustering']; strong = c['p'] < 0.01
        out.append({'id': f'cluster-{k}', 'strength': 'strong' if strong else 'suggestive', 'site': k,
            'en': f"{sites[k]['name'].split(',')[0]}: off-beat samples sit next to each other more often than chance allows, so they mark coherent patches rather than random noise.",
            'ru': f"{sites[k]['name'].split(',')[0]}: выбросы стоят рядом друг с другом чаще, чем при случайности, то есть отмечают связные участки, а не шум.",
            'how_en': f"{c['adjacent_pairs']} adjacent off-beat pairs among {c['flagged']} flagged samples; random relabelling gives {c['expected_pairs']} on average (p = {c['p']}, {c['permutations']:,} permutations).",
            'how_ru': f"{c['adjacent_pairs']} соседних пар среди {c['flagged']} выбросов; при случайной перестановке в среднем {c['expected_pairs']} (p = {c['p']}, {c['permutations']:,} перестановок)."})
    if scattered:
        out.append({'id': 'scattered', 'strength': 'none', 'site': None,
            'en': f"{names(sites, scattered)}: off-beat samples are scattered the way random noise would be. Treat a single flagged sample there as a lead, not a finding.",
            'ru': f"{names(sites, scattered)}: выбросы рассеяны так же, как случайный шум. Одиночная отмеченная точка там - повод проверить, а не находка.",
            'how_en': 'Same join-count permutation test; p >= 0.05 at each: ' + ', '.join(f"{sites[k]['name'].split(',')[0]} p = {sites[k]['clustering']['p']}" for k in scattered) + '.',
            'how_ru': 'Тот же перестановочный тест; p >= 0.05 на каждом: ' + ', '.join(f"{sites[k]['name'].split(',')[0]} p = {sites[k]['clustering']['p']}" for k in scattered) + '.'})

    for k in ok:
        t = sites[k]['trends']
        if not t or not t['samples']:
            continue
        top = t['strongest'][0]
        out.append({'id': f'trends-{k}', 'strength': 'strong', 'site': k, 'samples': [h['index'] for h in t['strongest'][:6]],
            'en': f"{sites[k]['name'].split(',')[0]}: {t['samples']} samples drift steadily away from their neighbours over {sites[k]['dates']} dates ({t['brightening']} brightening, {t['darkening']} darkening). These are the best candidates for real, gradual change.",
            'ru': f"{sites[k]['name'].split(',')[0]}: {t['samples']} точек устойчиво уходят от соседей за {sites[k]['dates']} дат ({t['brightening']} светлеют, {t['darkening']} темнеют). Это лучшие кандидаты на реальное постепенное изменение.",
            'how_en': f"Kendall trend test of peer z against time for each sample and channel ({t['tests']:,} tests), Benjamini-Hochberg false discovery rate 5%: at most {t['expected_false_at_most']} of {t['significant_tests']} detections are expected to be false. Strongest: {top['id']} {top['channel'].upper()} {top['slope_db_per_year']:+} dB/year relative to its neighbours. Repeated dates are correlated, which can overstate significance, so treat this as a ranking of candidates. Cause unverified.",
            'how_ru': f"Тест тренда Кендалла для z каждой точки и канала ({t['tests']:,} тестов), контроль доли ложных открытий 5% (Бенджамини-Хохберг): ожидается не более {t['expected_false_at_most']} ложных из {t['significant_tests']}. Сильнейшая: {top['id']} {top['channel'].upper()} {top['slope_db_per_year']:+} дБ/год относительно соседей. Соседние даты коррелированы, и значимость может быть завышена, поэтому это ранжирование кандидатов. Причина не проверена."})

    for k in ok:
        p = sites[k]['persistence']
        if p and p['lift'] and p['lift'] >= 5 and sites[k]['dates'] >= 10:
            out.append({'id': f'persistence-{k}', 'strength': 'strong', 'site': k,
                'en': f"{sites[k]['name'].split(',')[0]}: a flagged sample is {p['lift']:.0f}x more likely to be flagged again 12 days later. Most off-beat samples are permanently different objects, not events; a sample that newly leaves its neighbours is the better change signal.",
                'ru': f"{sites[k]['name'].split(',')[0]}: отмеченная точка в {p['lift']:.0f} раз чаще остаётся отмеченной через 12 дней. Большинство выбросов - просто другие по природе объекты, а не события; сигнал изменения - точка, которая впервые уходит от соседей.",
                'how_en': f"P(|z_HV| > 2.5 at the next date | flagged now) = {p['flag_again']} vs base rate {p['base_rate']}. {p['ever_flagged']} samples were flagged at least once, {p['flagged_half_or_more']} on half the dates or more.",
                'how_ru': f"P(|z_HV| > 2.5 на следующую дату | отмечена сейчас) = {p['flag_again']} при базовой частоте {p['base_rate']}. Хотя бы раз отмечено {p['ever_flagged']} точек, в половине дат и чаще - {p['flagged_half_or_more']}."})

    for k in ok:
        shifts = sites[k]['common_mode']
        if not shifts:
            continue
        def move(shift):
            vals = list(shift['median_shift_db'].values()); return sum(vals) / len(vals)
        en_list = ', '.join(f"{sh['to']} ({move(sh):+.1f} dB)" for sh in shifts)
        ru_list = ', '.join(f"{sh['to']} ({move(sh):+.1f} дБ)" for sh in shifts)
        many = len(shifts) > 1
        out.append({'id': f'common-{k}', 'strength': 'strong', 'site': k,
            'en': f"{sites[k]['name'].split(',')[0]}: the whole scene brightened or darkened at once on {en_list}, in every land-cover class. A scene-wide shift (calibration, processing or ground moisture) is not a local event; the neighbour comparison cancels it.",
            'ru': f"{sites[k]['name'].split(',')[0]}: вся сцена разом посветлела или потемнела {ru_list} во всех классах покрытия. Сдвиг всей сцены (калибровка, обработка или влажность) - не локальное событие; сравнение с соседями его гасит.",
            'how_en': ' '.join(f"Median HV change {sh['from']} -> {sh['to']}: " + ', '.join(f"{CLASSES[int(c)][0]} {v:+} dB" for c, v in sh['median_shift_db'].items()) + '.' for sh in shifts) + ' Flagged when every class with 20+ samples moves the same way by at least 2 dB.',
            'how_ru': ' '.join(f"Медианное изменение HV {sh['from']} -> {sh['to']}: " + ', '.join(f"{CLASSES[int(c)][1]} {v:+} дБ" for c, v in sh['median_shift_db'].items()) + '.' for sh in shifts) + ' Отмечается, когда все классы с 20+ точками сдвигаются в одну сторону не меньше чем на 2 дБ.'})

    floors = [(k, c, v) for k in ok if not sites[k]['common_mode'] for c, v in sites[k]['noise_floor'].items() if c in ('10', '50')]
    if floors:
        med = [v['median_db'] for _, _, v in floors]; p90 = [v['p90_db'] for _, _, v in floors]
        used = sorted({k for k, _, _ in floors}, key=SITES.index)
        out.append({'id': 'noise-floor', 'strength': 'strong', 'site': None,
            'en': f"Over 12 days a typical sample's HV moves by about {min(med):.1f}-{max(med):.1f} dB, and 1 in 10 moves more than {min(p90):.1f}-{max(p90):.1f} dB. A one-pair change smaller than ~{max(p90):.0f} dB cannot be told apart from noise.",
            'ru': f"За 12 дней HV типичной точки сдвигается примерно на {min(med):.1f}-{max(med):.1f} дБ, а каждая десятая - больше чем на {min(p90):.1f}-{max(p90):.1f} дБ. Изменение по одной паре меньше ~{max(p90):.0f} дБ не отличить от шума.",
            'how_en': f"Absolute HV difference between consecutive acquisitions <= 12 days apart, tree cover and built-up samples, sites without a scene-wide shift: {names(sites, used)}. Median and 90th percentile per site and class.",
            'how_ru': f"Модуль разности HV между соседними съёмками с интервалом <= 12 дней, лес и застройка, участки без сдвига всей сцены: {names(sites, used)}. Медиана и 90-й перцентиль по участку и классу."})

    paired = [k for k in ok if '10' in sites[k]['classes'] and '50' in sites[k]['classes']]
    if paired:
        hh_wins = [k for k in paired if sites[k]['classes']['50']['hh_db'] > sites[k]['classes']['10']['hh_db']]
        ratio_wins = [k for k in paired if sites[k]['classes']['10']['hv_db'] - sites[k]['classes']['10']['hh_db'] > sites[k]['classes']['50']['hv_db'] - sites[k]['classes']['50']['hh_db']]
        sign_p = stats.binomtest(len(ratio_wins), len(paired), 0.5, alternative='greater').pvalue
        out.append({'id': 'physics', 'strength': 'strong' if sign_p < 0.05 else 'suggestive', 'site': None,
            'en': f"The data behaves like real radar physics: relative to HH, trees return more HV (volume scattering in the canopy) than buildings do at {len(ratio_wins)} of {len(paired)} sites; buildings return brighter HH than trees at {len(hh_wins)} of {len(paired)}.",
            'ru': f"Данные ведут себя как настоящая физика радара: относительно HH лес даёт больше HV (объёмное рассеяние в кроне), чем застройка, на {len(ratio_wins)} из {len(paired)} участков; застройка ярче леса в HH на {len(hh_wins)} из {len(paired)}.",
            'how_en': f"Class medians of HH and HV over all dates at sites with both tree cover and built-up (WorldCover 2021). One-sided sign test for the cross-polarisation ratio: p = {r(sign_p, 3)}. Sites: {names(sites, paired)}.",
            'how_ru': f"Медианы HH и HV по классам за все даты на участках, где есть и лес, и застройка (WorldCover 2021). Односторонний знаковый тест для отношения кросс-поляризации: p = {r(sign_p, 3)}. Участки: {names(sites, paired)}."})

    coh = [k for k in paired if sites[k]['classes']['10']['coherence'] is not None and sites[k]['classes']['50']['coherence'] is not None]
    if coh:
        wins = [k for k in coh if sites[k]['classes']['50']['coherence'] > sites[k]['classes']['10']['coherence']]
        b = [sites[k]['classes']['50']['coherence'] for k in coh]; t = [sites[k]['classes']['10']['coherence'] for k in coh]
        out.append({'id': 'coherence', 'strength': 'strong' if len(wins) == len(coh) and len(coh) >= 4 else 'suggestive', 'site': None,
            'en': f"Ground motion is measurable in cities, much less under trees: interferometric coherence is higher on buildings ({min(b):.2f}-{max(b):.2f}) than on tree cover ({min(t):.2f}-{max(t):.2f}) at {len(wins)} of {len(coh)} sites.",
            'ru': f"Движение грунта измеримо в городах и гораздо хуже под деревьями: когерентность интерферометрии выше на застройке ({min(b):.2f}-{max(b):.2f}), чем на лесе ({min(t):.2f}-{max(t):.2f}), на {len(wins)} из {len(coh)} участков.",
            'how_en': f"Median GUNW coherence of one acquisition pair per site, by WorldCover class. Sites: {names(sites, coh)}.",
            'how_ru': f"Медианная когерентность GUNW по одной паре съёмок на участок, по классам WorldCover. Участки: {names(sites, coh)}."})

    short = [k for k in SITES if k in sites and sites[k]['dates'] < 3]
    if short:
        out.append({'id': 'short-records', 'strength': 'none', 'site': None,
            'en': f"{names(sites, short)} have only two acquisitions so far: one comparison each, no trend or persistence test is possible yet.",
            'ru': f"По {names(sites, short)} пока только две съёмки: одно сравнение, проверить тренд или устойчивость пока нельзя.",
            'how_en': 'Trend tests need at least 10 dates; persistence needs 3.',
            'how_ru': 'Для теста тренда нужно не меньше 10 дат, для устойчивости - 3.'})

    # Headline order for a first visit: the strongest substantive results, then method checks,
    # then what the data cannot support. A site's own findings are moved up by the page when it is open.
    priority = ['trends', 'physics', 'cluster', 'coherence', 'noise', 'persistence', 'common', 'calibration', 'quality', 'scattered', 'short']
    order = {'strong': 0, 'suggestive': 1, 'issue': 2, 'none': 3}
    out.sort(key=lambda f: (f['strength'] != 'strong' and order[f['strength']], priority.index(f['id'].split('-')[0])))
    return out


def main():
    rng = np.random.default_rng(20260415)
    sites, hashes = {}, {}
    for k in SITES:
        raw = (ROOT / 'data' / f'{k}.json').read_bytes()
        hashes[k] = hashlib.sha256(raw).hexdigest()
        sites[k] = analyse(json.loads(raw), rng)
    result = {'schema_version': 1, 'method': 'scripts/findings.py', 'inputs_sha256': hashes,
              'notes': 'Measured NISAR GCOV and GUNW samples only. No interpolation, gap filling or simulation. Causes are not attributed.',
              'findings': build_findings(sites), 'sites': sites}
    (ROOT / 'data' / 'findings.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    for f in result['findings']:
        print(f"[{f['strength']:10s}] {f['en']}")


if __name__ == '__main__':
    main()
