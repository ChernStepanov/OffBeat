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
    const X = i => PAD.l + (i / (dates.length - 1)) * (w - PAD.l - PAD.r);
    const Y = v => PAD.t + (1 - (v - lo) / (hi - lo)) * (h - PAD.t - PAD.b);
    g.font = "12.5px W95FA, Tahoma, sans-serif"; g.fillStyle = "#333"; g.strokeStyle = "#e2e2e2"; g.lineWidth = 1;
    const step = niceStep((hi - lo) / 4);
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
      const y = Math.round(Y(v)) + 0.5;
      g.beginPath(); g.moveTo(PAD.l, y); g.lineTo(w - PAD.r, y); g.stroke();
      g.textAlign = "right"; g.fillText(+v.toFixed(1), PAD.l - 4, y + 3);
    }
    g.textAlign = "center";
    for (let i = 0; i < dates.length; i += Math.ceil(dates.length / 6)) g.fillText(dates[i].slice(2, 7), X(i), h - 6);
    g.strokeStyle = "#808080"; g.strokeRect(PAD.l + 0.5, PAD.t + 0.5, w - PAD.l - PAD.r, h - PAD.t - PAD.b);
    return { X, Y };
  }

  function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x))); const m = x / p; return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p; }

  // real series have gaps (NaN): ranges skip them, lines break at them
  const fin = a => a.filter(Number.isFinite);
  const range = (a, pad) => { const f = fin(a); return f.length ? [Math.floor(Math.min(...f) - pad), Math.ceil(Math.max(...f) + pad)] : [-1, 1]; };

  function band(g, X, Y, med, sd, k) {
    g.fillStyle = "rgba(150,150,150,.28)"; g.beginPath();
    const ok = med.map((m, i) => i).filter(i => Number.isFinite(med[i]) && Number.isFinite(sd[i]));
    ok.forEach(i => g.lineTo(X(i), Y(med[i] + k * sd[i])));
    ok.slice().reverse().forEach(i => g.lineTo(X(i), Y(med[i] - k * sd[i])));
    g.closePath(); g.fill();
    g.strokeStyle = "#8a8a8a"; g.setLineDash([3, 3]); line(g, X, Y, med); g.setLineDash([]);
  }
  function line(g, X, Y, arr) { g.beginPath(); let up = true; arr.forEach((v, i) => { if (!Number.isFinite(v)) { up = true; return; } up ? g.moveTo(X(i), Y(v)) : g.lineTo(X(i), Y(v)); up = false; }); g.stroke(); }
  function dots(g, X, Y, arr, c) { g.fillStyle = c; arr.forEach((v, i) => Number.isFinite(v) && g.fillRect(X(i) - 1.5, Y(v) - 1.5, 3, 3)); }
  function marker(g, X, h, i, label) {
    if (i == null || i < 0) return;
    const x = Math.round(X(i)) + 0.5;
    g.strokeStyle = "#000"; g.setLineDash([2, 2]); g.beginPath(); g.moveTo(x, PAD.t); g.lineTo(x, h - PAD.b); g.stroke(); g.setLineDash([]);
    if (label) { g.fillStyle = "#000"; g.textAlign = "left"; g.fillText(label, x + 3, PAD.t + 10); }
  }
  function playhead(g, X, h, i) {
    const x = Math.round(X(i)) + 0.5; g.strokeStyle = "#ffcc00"; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x, PAD.t); g.lineTo(x, h - PAD.b); g.stroke(); g.lineWidth = 1;
  }

  function backscatter(cv, dates, p, sinceIdx, head) {
    const { g, w, h } = setup(cv);
    const all = p.hh.concat(p.hv, p.peer.hh_med.map((m, i) => m + 2 * p.peer.hh_sd[i]), p.peer.hv_med.map((m, i) => m - 2 * p.peer.hv_sd[i]));
    const [lo, hi] = range(all, 1);
    const { X, Y } = frame(g, w, h, dates, lo, hi);
    band(g, X, Y, p.peer.hh_med, p.peer.hh_sd, 2);
    band(g, X, Y, p.peer.hv_med, p.peer.hv_sd, 2);
    g.lineWidth = 1.6;
    g.strokeStyle = "#000080"; line(g, X, Y, p.hh); dots(g, X, Y, p.hh, "#000080");
    g.strokeStyle = "#c00000"; line(g, X, Y, p.hv); dots(g, X, Y, p.hv, "#c00000");
    g.lineWidth = 1;
    marker(g, X, h, sinceIdx, sinceIdx != null ? "off-beat" : "");
    if (head != null) playhead(g, X, h, head);
  }

  function displacement(cv, dates, p, sinceIdx, head) {
    const { g, w, h } = setup(cv);
    if (!p.disp) {
      g.fillStyle = "#555"; g.font = "12.5px W95FA, Tahoma, sans-serif"; g.textAlign = "center";
      g.fillText("No GUNW interferogram covers this pixel yet.", w / 2, h / 2 + 4);
      return;
    }
    const all = p.disp.concat(p.peer_disp.map(v => v + 2.4), p.peer_disp.map(v => v - 2.4));
    const [lo, hi] = range(all, 0);
    const { X, Y } = frame(g, w, h, dates, lo, hi);
    band(g, X, Y, p.peer_disp, p.peer_disp.map(() => 1.2), 2);
    g.lineWidth = 1.6; g.strokeStyle = "#d86b00"; line(g, X, Y, p.disp); dots(g, X, Y, p.disp, "#d86b00"); g.lineWidth = 1;
    marker(g, X, h, sinceIdx, "");
    if (head != null) playhead(g, X, h, head);
  }

  return { backscatter, displacement };
})();
