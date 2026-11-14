"""Rebuild the public casebook from stored measurements and reviewed evidence.
No network, detector tuning, or new ground-truth labels. Run from repository root.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT / path).read_text())

def tr(en, ru):
    return {'en': en, 'ru': ru}


def build():
    paths = ['data/amazon.json', 'data/amazon/optical/index.json',
             'data/analysis/amazon-dense-pair.json',
             'data/benchmark/amazon-v1/evidence.json',
             'archive/preview-2026-11-14/data/amazon/positive-eval/results.json',
             'docs/amazon-benchmark-v1.md',
             'archive/preview-2026-11-14/docs/amazon-positive-eval.md',
             'data/amazon-spatial-external-audit-v2.json',
             'docs/amazon-external-audit-v2.md']
    site, optical, dense, evidence, positive = [read(p) for p in paths[:5]]
    specs = [
        ('amazon-hv-step', 175, 'unknown',
         tr('A radar change worth checking', 'Изменение радара, которое стоит проверить'),
         tr('HV fell between 23 August and 4 September. Does that mean forest loss?', 'HV снизился между 23 августа и 4 сентября. Означает ли это потерю леса?'),
         tr('The native 20 m cell fell by 7.420 dB; its 3 x 3 neighbourhood median fell by 4.122 dB. These are radar measurements, not independent confirmation.', 'На исходной сетке 20 м HV упал на 7.420 dB, медиана окрестности 3 x 3 — на 4.122 dB. Это радарные измерения, а не независимое подтверждение.'),
         tr('The dated optical pair spans a wider interval than the radar pair. No reviewed independent evidence establishes forest loss at this sample. Missing alerts do not establish stability.', 'Датированная оптика охватывает более широкий интервал, чем радарная пара. Проверенные независимые данные не устанавливают потерю леса в этой точке. Отсутствие алертов не доказывает стабильность.'),
         tr('Cause unknown. Moisture, vegetation changes and radar acquisition effects remain possible; none is established.', 'Причина неизвестна. Возможны влажность, изменения растительности и эффекты радарной съёмки; ни одна причина не установлена.'),
         tr('Prioritise independent image review or field inspection. Obtain additional clear imagery and SAR history before classifying a disturbance.', 'Приоритет — независимая проверка снимков или участка. Нужны дополнительные ясные снимки и SAR-история до классификации события.'),
         ('2026-08-14', '2026-09-21'), [2, 3]),
        ('amazon-visible-clearing', 142, 'visible_change_insufficient_sar',
         tr('Visible clearing, missing radar history', 'Видимая расчистка, недостаточная история радара'),
         tr('A real visible change can still be unsuitable for testing a detector.', 'Реальное видимое изменение может не подходить для проверки детектора.'),
         tr('The reviewed clearing occurred after 5 July and by 4 August. At most one SAR date could precede it; the detector requires two observations on each side.', 'По визуальной проверке расчистка произошла после 5 июля и не позднее 4 августа. До неё могла быть максимум одна SAR-дата; детектор требует минимум две с каждой стороны.'),
         tr('Archived RGB review shows canopy in early July and clearing by 4 August. The GLAD alert is dated 24 August, at least 20 days after visible clearing; it is not the event date.', 'Архивный разбор RGB показывает кроны в начале июля и расчистку к 4 августа. Алерт GLAD датирован 24 августа — минимум на 20 дней позже видимой расчистки; это не дата события.'),
         tr('Visible clearing is supported by the archived review. Detector performance cannot be evaluated on this case: no guaranteed pre-event SAR history.', 'Видимая расчистка подтверждается архивным разбором. Оценить качество детектора на этом случае нельзя: нет гарантированной SAR-истории до события.'),
         tr('Acquire earlier valid NISAR dates or choose a later independently dated event. Do not count this as a successful detection or a measured recall failure.', 'Получить более ранние валидные NISAR-даты или выбрать более позднее независимо датированное событие. Не считать этот случай успешной детекцией или измеренным провалом полноты.'),
         ('2026-07-03', '2026-08-04'), [0, 1]),
        ('amazon-transient', 897, 'likely_false_persistent_change',
         tr('A temporary signal, not verified forest loss', 'Временный сигнал без подтверждённой потери леса'),
         tr('Check an apparent anomaly against both the whole series and optical evidence.', 'Сверьте предполагаемую аномалию со всем рядом и оптикой.'),
         tr('The archived review found the drop in only 2 of 6 leave-one-date-out runs. The latest peer deviation returned to about -0.18.', 'Архивный разбор сохранил падение лишь в 2 из 6 прогонов с исключением одной даты. Последнее отклонение от соседей вернулось примерно к -0.18.'),
         tr('Tree cover around the point persists in all five reviewed RGB dates. This is a retrospective visual review, not a blind negative control.', 'Древесный покров вокруг точки сохраняется на всех пяти проверенных RGB-датах. Это ретроспективный визуальный разбор, а не слепой отрицательный контроль.'),
         tr('Likely false selection of persistent change. Neither instrument noise nor a specific physical cause has been demonstrated.', 'Вероятное ложное выделение устойчивого изменения. Инструментальный шум и конкретная физическая причина не доказаны.'),
         tr('Keep monitoring; do not report confirmed clearing. Use independently labelled control events to evaluate false positives.', 'Продолжить наблюдение; не сообщать о подтверждённой вырубке. Для оценки ложных срабатываний нужны независимо размеченные контрольные события.'),
         ('2026-07-03', '2026-09-21'), [0, 5]),
    ]
    cases = []
    for key, index, status, title, question, observed, independent, interpretation, action, images, pair in specs:
        p = site['pixels'][index]
        entries = [next(e for e in optical['entries'] if e['date'] == date) for date in images]
        sources = ['data/amazon.json', 'data/amazon/optical/index.json', 'docs/amazon-benchmark-v1.md']
        sources += [paths[2], paths[7], paths[8]] if index == 175 else ([paths[4], paths[6]] if index == 142 else [paths[3]])
        cases.append(dict(id=key, site='amazon', sample_index=index, sample_id=p['id'], status=status,
                          title=title, question=question, observed=observed, independent=independent,
                          interpretation=interpretation, action=action, radar_pair=pair,
                          optical=entries, sources=sources,
                          review_independence='retrospective development review; not blind test labels'))
    return dict(schema_version=1, id='amazon-casebook-v1',
                evaluation=dict(eligible_positive_events=0, independently_labelled_negative_controls=0,
                                independent_test_groups=0, precision=None, recall=None, false_positive_rate=None),
                policy='Radar corroboration is not independent evidence. No alert absence becomes a negative label. No event area is inferred from sample spacing.',
                input_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}, cases=cases)

if __name__ == '__main__':
    target = ROOT / 'data/cases/amazon-v1.json'
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n')
    print(target.relative_to(ROOT))
