// Sonification: one beat per acquisition.
// Peers: a soft click on the beat and a quiet tone at the peer median.
// Pixel: a tone pitched from its own curve, pushed late and detuned by how far it strays (|z| per date).
window.OB = window.OB || {};

OB.sonify = (function () {
  let ctx = null, nodes = [], timer = null;
  const BEAT = 0.22; // seconds per acquisition

  const hz = (db, lo, hi) => 180 * Math.pow(2, 2.5 * Math.min(1, Math.max(0, (db - lo) / (hi - lo)))); // ~180..1000 Hz

  function tone(t, f, dur, type, gain, pan, detune) {
    const o = ctx.createOscillator(), a = ctx.createGain(), p = ctx.createStereoPanner();
    o.type = type; o.frequency.value = f; o.detune.value = detune || 0;
    a.gain.setValueAtTime(0, t); a.gain.linearRampToValueAtTime(gain, t + 0.01); a.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    p.pan.value = pan;
    o.connect(a).connect(p).connect(ctx.destination); o.start(t); o.stop(t + dur + 0.02); nodes.push(o);
  }
  function click(t) {
    const len = Math.floor(ctx.sampleRate * 0.02), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 6);
    const s = ctx.createBufferSource(), a = ctx.createGain(); a.gain.value = 0.35;
    s.buffer = buf; s.connect(a).connect(ctx.destination); s.start(t); nodes.push(s);
  }

  // series: {pix:[], med:[], sd:[]} in the channel that carries the style
  function play(series, onStep, onEnd) {
    stop();
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    const all = series.pix.concat(series.med).filter(Number.isFinite);
    if (!all.length) { onEnd && onEnd(); return; }
    const lo = Math.min(...all), hi = Math.max(...all) + 0.01;
    const t0 = ctx.currentTime + 0.08;
    series.pix.forEach((v, i) => {
      if (!Number.isFinite(v) || !Number.isFinite(series.med[i]) || !Number.isFinite(series.sd[i])) return;
      const t = t0 + i * BEAT;
      const z = Math.min(4, Math.abs(v - series.med[i]) / (series.sd[i] || 1));
      click(t);
      tone(t, hz(series.med[i], lo, hi), BEAT * 0.9, "sine", 0.06, -0.5, 0);
      const late = z > 1.5 ? z * 0.025 : 0;            // slips off the beat
      tone(t + late, hz(v, lo, hi), BEAT * 0.8, "triangle", 0.16, 0.5, z > 1.5 ? z * 22 : 0); // and goes sour
    });
    let i = 0;
    onStep && onStep(0);
    timer = setInterval(() => {
      i++;
      if (i >= series.pix.length) { stop(); onEnd && onEnd(); return; }
      onStep && onStep(i);
    }, BEAT * 1000);
  }

  function stop() {
    clearInterval(timer); timer = null;
    nodes.forEach(n => { try { n.stop(); } catch (e) {} }); nodes = [];
  }

  return { play, stop, playing: () => timer !== null };
})();
