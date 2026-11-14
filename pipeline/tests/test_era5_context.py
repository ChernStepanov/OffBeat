from scripts.era5_context import summarize


def test_windows_exclude_acquisition_day_and_future():
    dates=['2026-01-04']
    daily={'time':['2026-01-01','2026-01-02','2026-01-03','2026-01-04','2026-01-05'],
           'precipitation_sum':[1,2,3,100,100]}
    result=summarize(dates,daily)[0]
    assert result['previous_1_utc_days_mm']==3
    assert result['previous_3_utc_days_mm']==6
    assert result['previous_7_utc_days_mm'] is None


def test_missing_day_does_not_become_zero():
    daily={'time':['2026-01-01','2026-01-02','2026-01-03'], 'precipitation_sum':[0,None,2]}
    result=summarize(['2026-01-04'],daily)[0]
    assert result['previous_1_utc_days_mm']==2
    assert result['previous_3_utc_days_mm'] is None
