// Plain canvas time-series plots: pixel lines over a grey peer band (median ± 2σ).
window.OB = window.OB || {};

OB.chart = (function () {
  const PAD = { l: 38, r: 10, t: 8, b: 20 };

  function setup(cv) {
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.height / (cv._dpr || 1);
    cv._dpr = dpr; cv.width = w * dpr; cv.height = h * dpr; cv.style.height = h + "px";
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h);
    return { g, w, h };
  }

  function frame(g, w, h, dates, lo, hi, unit) {
    const times = dates.map(d => Date.parse(d));
    const duration = times.at(-1) - times[0];
    const X = i => PAD.l + (duration > 0 ? (times[i] - times[0]) / duration : 0.5) * (w - PAD.l - PAD.r);
    const Y = v => PAD.t + (1 - (v - lo) / (hi - lo)) * (h - PAD.t - PAD.b);
    g.font = "12.5px W95FA, Tahoma, sans-serif"; g.fillStyle = "#333"; g.strokeStyle = "#e2e2e2"; g.lineWidth = 1;
    const step = niceStep((hi - lo) / 4);
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
      const y = Math.round(Y(v)) + 0.5;
      g.beginPath(); g.moveTo(PAD.l, y); g.lineTo(w - PAD.r, y); g.stroke();
      g.textAlign = "right"; g.fillText(+v.toFixed(1), PAD.l - 4, y + 3);
    }
    g.textAlign = "center";
    // date ticks; the ones at the ends hug the frame instead of spilling past it
    for (let i = 0; i < dates.length; i += Math.ceil(dates.length / 6)) {
      const x = X(i), half = g.measureText(dates[i].slice(2, 7)).width / 2;
      g.textAlign = x - half < 0 ? "left" : x + half > w ? "right" : "center";
      g.fillText(dates[i].slice(2, 7), g.textAlign === "left" ? 0 : g.textAlign === "right" ? w : x, h - 6);
    }
    g.textAlign = "center";
    g.strokeStyle = "#808080"; g.strokeRect(PAD.l + 0.5, PAD.t + 0.5, w - PAD.l - PAD.r, h - PAD.t - PAD.b);
    return { X, Y };
  }

  function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x))); const m = x / p; return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p; }

  // real series have gaps (NaN): ranges skip them, lines break at them
  const fin = a => a.filter(Number.isFinite);
  const range = (a, pad) => { const f = fin(a); return f.length ? [Math.floor(Math.min(...f) - pad), Math.ceil(Math.max(...f) + pad)] : [-1, 1]; };

  function band(g, X, Y, med, sd, k) {
    g.fillStyle = "rgba(150,150,150,.28)";
    for (let start = 0; start < med.length;) {
      while (start < med.length && !(Number.isFinite(med[start]) && Number.isFinite(sd[start]))) start++;
      let end = start;
      while (end < med.length && Number.isFinite(med[end]) && Number.isFinite(sd[end])) end++;
      if (end > start) {
        g.beginPath();
        for (let i = start; i < end; i++) g.lineTo(X(i), Y(med[i] + k * sd[i]));
        for (let i = end - 1; i >= start; i--) g.lineTo(X(i), Y(med[i] - k * sd[i]));
        g.closePath(); g.fill();
      }
      start = end + 1;
    }
    g.strokeStyle = "#8a8a8a"; g.setLineDash([3, 3]); line(g, X, Y, med); g.setLineDash([]);
  }
  function line(g, X, Y, arr) { let active = false; g.beginPath(); arr.forEach((v, i) => { if (!Number.isFinite(v)) { active = false; return; } if (active) g.lineTo(X(i), Y(v)); else g.moveTo(X(i), Y(v)); active = true; }); g.stroke(); }
  function dots(g, X, Y, arr, c) { g.fillStyle = c; arr.forEach((v, i) => { if (Number.isFinite(v)) g.fillRect(X(i) - 1.5, Y(v) - 1.5, 3, 3); }); }
  function empty(g, w, h, message) { g.fillStyle = '#555'; g.font = '11px Tahoma, sans-serif'; g.textAlign = 'center'; g.fillText(message, w / 2, h / 2); }
  function marker(g, X, h, i, label) {
    if (i == null || i < 0) return;
    const x = Math.round(X(i)) + 0.5;
    g.strokeStyle = "#000"; g.setLineDash([2, 2]); g.beginPath(); g.moveTo(x, PAD.t); g.lineTo(x, h - PAD.b); g.stroke(); g.setLineDash([]);
    if (label) { g.fillStyle = "#000"; g.textAlign = "left"; g.fillText(label, x + 3, PAD.t + 10); }
  }
  function playhead(g, X, h, i) {
    const x = Math.round(X(i)) + 0.5; g.strokeStyle = "#67217a"; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x, PAD.t); g.lineTo(x, h - PAD.b); g.stroke(); g.lineWidth = 1;
  }

  function backscatter(cv, dates, p, sinceIdx, head) {
    const { g, w, h } = setup(cv);
    const bound = (med, sd, sign) => med.map((m,i) => Number.isFinite(m) && Number.isFinite(sd[i]) ? m + sign * 2 * sd[i] : null);
    const all = p.hh.concat(p.hv, bound(p.peer.hh_med,p.peer.hh_sd,1), bound(p.peer.hv_med,p.peer.hv_sd,-1)).filter(Number.isFinite);
    if (!dates.length || !all.length) { empty(g,w,h,'No GCOV HH/HV measurements loaded for this pixel.'); return; }
    const lo = Math.floor(Math.min(...all) - 1), hi = Math.ceil(Math.max(...all) + 1);
    const { X, Y } = frame(g, w, h, dates, lo, hi);
    band(g, X, Y, p.peer.hh_med, p.peer.hh_sd, 2);
    band(g, X, Y, p.peer.hv_med, p.peer.hv_sd, 2);
    g.lineWidth = 1.6;
    g.strokeStyle = "#000080"; line(g, X, Y, p.hh); dots(g, X, Y, p.hh, "#000080");
    g.strokeStyle = "#c00000"; line(g, X, Y, p.hv); dots(g, X, Y, p.hv, "#c00000");
    g.lineWidth = 1;
    marker(g, X, h, sinceIdx, sinceIdx != null ? "off-beat" : "");
    if (head != null) playhead(g, X, h, head);
    if (!p.hh.some(Number.isFinite) || !p.hv.some(Number.isFinite)) empty(g,w,28, !p.hh.some(Number.isFinite) ? 'HH unavailable' : 'HV unavailable');
  }

  function displacement(cv, dates, p, sinceIdx, head) {
    const { g, w, h } = setup(cv);
    if (!dates.length || !p.disp || !p.disp.some(Number.isFinite)) {
      g.fillStyle = "#555"; g.font = "12.5px W95FA, Tahoma, sans-serif"; g.textAlign = "center";
      g.fillText("No validated GUNW displacement for this pixel.", w / 2, h / 2 + 4);
      return;
    }
    const all = p.disp.concat(p.peer_disp || []).filter(Number.isFinite);
    const lo = Math.floor(Math.min(...all) - 1), hi = Math.ceil(Math.max(...all) + 1);
    const { X, Y } = frame(g, w, h, dates, lo, hi);
    if (p.peer_disp && p.peer_disp_sd) band(g, X, Y, p.peer_disp, p.peer_disp_sd, 2);
    g.lineWidth = 1.6; g.strokeStyle = "#d86b00"; line(g, X, Y, p.disp); dots(g, X, Y, p.disp, "#d86b00"); g.lineWidth = 1;
    marker(g, X, h, sinceIdx, "");
    if (head != null) playhead(g, X, h, head);
  }

  // Sentinel-1 C band over its own, longer record; the shaded span is when NISAR measured this site
  function cband(cv, dates, vv, vh, nisarDates) {
    const { g, w, h } = setup(cv);
    const [lo, hi] = range(vv.concat(vh), 1);
    const { X, Y } = frame(g, w, h, dates, lo, hi);
    if (nisarDates && nisarDates.length) {
      const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[dates.length - 1]);
      const x = d => PAD.l + (Date.parse(d) - t0) / (t1 - t0) * (w - PAD.l - PAD.r);
      const a = Math.max(PAD.l, x(nisarDates[0])), b = Math.min(w - PAD.r, x(nisarDates[nisarDates.length - 1]));
      if (b > a) { g.fillStyle = "rgba(255,204,0,.25)"; g.fillRect(a, PAD.t, Math.max(2, b - a), h - PAD.t - PAD.b); }
    }
    g.lineWidth = 1.4;
    g.strokeStyle = "#007a1f"; line(g, X, Y, vv); dots(g, X, Y, vv, "#007a1f");
    g.strokeStyle = "#7a5c00"; line(g, X, Y, vh); dots(g, X, Y, vh, "#7a5c00");
    g.lineWidth = 1;
  }

  // OPERA is an independent Sentinel-1 LOS measurement, not a NISAR vertical rate.
  function opera(cv, dates, values) {
    const { g, w, h } = setup(cv);
    if (!dates.length || !values.some(Number.isFinite)) { empty(g,w,h,'No quality-accepted OPERA samples.'); return; }
    const [lo,hi] = range(values, 1);
    const {X,Y} = frame(g,w,h,dates,lo,hi);
    g.lineWidth = 1.6; g.strokeStyle = '#006a73'; line(g,X,Y,values); dots(g,X,Y,values,'#006a73'); g.lineWidth = 1;
  }

  // a plot with nothing to show says so, instead of an empty white box
  function placeholder(cv, message) {
    const { g, w, h } = setup(cv);
    g.fillStyle = "#555"; g.font = "12.5px W95FA, Tahoma, sans-serif"; g.textAlign = "center";
    g.fillText(message, w / 2, h / 2 + 4);
  }

  return { backscatter, displacement, cband, opera, empty: placeholder };
})();
