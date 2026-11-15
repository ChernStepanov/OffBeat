"""Write data.js for the video page from measured files. Run from the repository root."""
import json
s = json.load(open('data/mexico.json')); f = json.load(open('data/findings.json'))
p = s['pixels'][258]  # MEX r8 c2: the steepest Mexico City trend with q < 0.001
counts = [sum(1 for q in s['pixels'] if q['z_hv'][i] is not None and abs(q['z_hv'][i]) >= 2.5 and q['cover'] != 80) for i in range(len(s['dates']))]
d = {'dates': s['dates'], 'id': p['id'], 'hv': p['hv'], 'med': p['peer']['hv_med'], 'sd': p['peer']['hv_sd'], 'z': p['z_hv'], 'counts': counts,
     'samples': sum(x['clustering']['valid'] for x in f['sites'].values()), 'sites': len(f['sites']),
     'trend': f['sites']['mexico']['trends']['samples'], 'p_cluster': f['sites']['mexico']['clustering']['p'],
     'gnss': f['opera_vs_gnss']['gnss_up_cm_per_year'], 'opera': f['opera_vs_gnss']['opera_los_cm_per_year_common'], 'tied': f['opera_tied']['percentiles_5_50_95']}
open('docs/submission/video/data.js', 'w').write('window.D=' + json.dumps(d) + ';')
