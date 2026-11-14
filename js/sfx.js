// Interface sounds in a late-90s desktop spirit, synthesized here with WebAudio (no sampled files).
// They carry meaning: an in-step pixel answers with a clean ding, an off-beat pixel with a sour, late one.
window.OB = window.OB || {};

OB.sfx = (function () {
  const KEY = "offbeat.sound";
  let ctx = null, master = null, started = false;
  let on = true;
  try { on = localStorage.getItem(KEY) !== "off"; } catch (e) { /* private mode: keep default */ }

  function audio() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0.3;
      // a touch of room so tones do not sound like a test signal
      const delay = ctx.createDelay(), fb = ctx.createGain(), wet = ctx.createGain();
      delay.delayTime.value = 0.07; fb.gain.value = 0.12; wet.gain.value = 0.06;
      master.connect(ctx.destination);
      master.connect(delay); delay.connect(fb); fb.connect(delay); delay.connect(wet); wet.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  // one enveloped oscillator
  function tone(t, f, dur, { type = "sine", gain = 0.2, attack = 0.005, detune = 0, slideTo = null, lp = null } = {}) {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(f, t); o.detune.value = detune;
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(gain, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    let node = o.connect(g);
    if (lp) { const f2 = ctx.createBiquadFilter(); f2.type = "lowpass"; f2.frequency.value = lp; g.connect(f2); node = f2; }
    node.connect(master);
    o.start(t); o.stop(t + dur + 0.05);
  }

  // a struck bell: fundamental plus two inharmonic partials
  function bell(t, f, dur = 0.7, gain = 0.16, detune = 0) {
    tone(t, f, dur, { gain, detune });
    tone(t, f * 2.76, dur * 0.5, { gain: gain * 0.35, detune });
    tone(t, f * 5.4, dur * 0.25, { gain: gain * 0.12, detune });
  }

  function noise(t, dur, gain, hp = 1500, lp = 0) {
    const len = Math.max(1, Math.floor(ctx.sampleRate * dur)), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    f.type = "highpass"; f.frequency.value = hp; g.gain.value = gain;
    let tail = s.connect(f);
    if (lp) { const l = ctx.createBiquadFilter(); l.type = "lowpass"; l.frequency.value = lp; tail = tail.connect(l); }
    s.buffer = buf; tail.connect(g).connect(master); s.start(t);
  }

  const SOUNDS = {
    // mechanical press of a raised button
    click: t => { noise(t, 0.006, 0.16, 900, 5000); noise(t + 0.045, 0.004, 0.06, 900, 5000); },
    // checkbox / list tick, lighter than a click
    tick: t => noise(t, 0.004, 0.09, 1500, 6000),
    // information: a clear two-partial bell
    ding: t => bell(t, 1318.5, 0.6, 0.14),
    // going back: the same bell a fourth lower
    dong: t => bell(t, 987.8, 0.6, 0.13),
    // a window opens: quick rising sweep
    open: t => { tone(t, 280, 0.16, { type: "triangle", gain: 0.12, slideTo: 1100, lp: 2500 }); noise(t, 0.08, 0.05, 4000); },
    // a window closes: the sweep falling
    close: t => tone(t, 1000, 0.14, { type: "triangle", gain: 0.1, slideTo: 260, lp: 2500 }),
    // an in-step pixel: one clean note
    instep: t => bell(t, 880, 0.22, 0.05),
    // an off-beat pixel: the same note, then a sour one arriving late
    offbeat: t => { bell(t, 880, 0.22, 0.05); bell(t + 0.08, 932.3, 0.3, 0.045, 18); },
    // something failed: a dull dissonant chord
    error: t => { [233, 247, 311].forEach(f => tone(t, f, 0.35, { type: "square", gain: 0.03, lp: 700 })); },
    // start-up: a slow, warm rising chord
    startup: t => {
      [311.1, 466.2, 587.3, 698.5, 784].forEach((f, i) => {
        tone(t + i * 0.09, f, 1.5 - i * 0.12, { type: "triangle", gain: 0.035, attack: 0.06, lp: 1800 });
        tone(t + i * 0.09, f, 1.5 - i * 0.12, { type: "sine", gain: 0.025, attack: 0.06, detune: 7 });
      });
    },
    // end of the tour: a short fanfare
    fanfare: t => {
      [[523.3, 0], [659.3, 0.1], [784, 0.2], [1046.5, 0.32]].forEach(([f, d]) =>
        tone(t + d, f, d === 0.32 ? 0.9 : 0.22, { type: "sawtooth", gain: 0.06, lp: 2400, attack: 0.01 }));
      bell(t + 0.32, 2093, 0.9, 0.05);
    }
  };

  let lastAt = 0, lastName = "";
  const log = [];                       // last sounds played, for checking the wiring in a console
  function play(name) {
    if (!on || !SOUNDS[name]) return;
    if (OB.sonify && OB.sonify.playing && OB.sonify.playing()) return;   // never talk over the pixel player
    audio();
    const now = ctx.currentTime;
    if (name === lastName && now - lastAt < 0.05) return;                // one gesture, one sound
    lastAt = now; lastName = name;
    log.push(name); if (log.length > 20) log.shift();
    SOUNDS[name](now + 0.01);
  }

  // browsers allow audio only after a gesture: greet on the first one
  function firstGesture(e) {
    if (started) return;
    started = true;
    if (on) { audio(); SOUNDS.startup(ctx.currentTime + 0.02); lastAt = ctx.currentTime; lastName = "startup"; log.push("startup"); }
  }
  window.addEventListener("pointerdown", firstGesture, { once: true, capture: true });
  window.addEventListener("keydown", firstGesture, { once: true, capture: true });

  // generic controls get their sound from the markup, so app code only signals meaning
  document.addEventListener("click", e => {
    if (!started) return;
    const el = e.target.closest("button, a, input[type=checkbox], [role=button]");
    if (!el || el.disabled || el.dataset.sfx === "none") return;
    if (el.dataset.sfx) return play(el.dataset.sfx);
    if (el.matches("input[type=checkbox]")) return play("tick");
    play("click");
  }, true);

  function set(v) {
    on = v;
    try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (e) { /* ignore */ }
    if (on) { audio(); SOUNDS.click(ctx.currentTime + 0.01); }
  }

  return { play, set, isOn: () => on, log: () => log.slice() };
})();

// status-bar speaker: mute and unmute, remembered per browser
(function () {
  function wire() {
    const b = document.getElementById("sb-sound"); if (!b) return;
    const show = () => {
      b.setAttribute("aria-pressed", String(OB.sfx.isOn()));
      document.getElementById("sb-sound-label").textContent = OB.sfx.isOn() ? "Sound on" : "Sound off";
    };
    b.addEventListener("click", () => { OB.sfx.set(!OB.sfx.isOn()); show(); });
    show();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();
})();
