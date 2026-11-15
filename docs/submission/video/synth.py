"""Soundtrack for the OffBeat video, synthesised on the same 0.145 s grid as the visuals.

The melodic line in the pixel-card scene is the real sonification of NISAR sample MEX r8 c2,
using the mapping of js/sonify.js: neighbours play a sine at their median, the sample plays a
triangle at its own value, late and detuned when it strays from them (|z| > 1.5).
"""
import json, re, wave
import numpy as np

SR = 44100
S = 0.145; Q = 4 * S
SC = [0, 6 * Q, 13 * Q, 21 * Q, 29 * Q, 38 * Q, 46 * Q, 51 * Q]
END = SC[7]
N = int(END * SR) + 1
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(7)
D = json.loads(re.sub(r'^window\.D=|;$', '', open('data.js').read().strip()))


def add(sig, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N: return
    sig = sig[: N - i] * gain
    L[i:i + len(sig)] += sig * np.sqrt((1 - pan) / 2)
    R[i:i + len(sig)] += sig * np.sqrt((1 + pan) / 2)


def env(n, a=0.002, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def tone(f, dur, kind='sine', a=0.005, d=0.3, detune=0.0):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f * 2 ** (detune / 1200)
    ph = 2 * np.pi * f * t
    w = {'sine': np.sin(ph), 'tri': 2 / np.pi * np.arcsin(np.sin(ph)),
         'saw': 2 * ((f * t) % 1) - 1, 'square': np.sign(np.sin(ph))}[kind]
    return w * env(n, a, d)


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR); y = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x): acc = (1 - a) * v + a * acc; y[i] = acc
    return y


def kick(gain=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16) * gain


def noise(dur, d, hp=True):
    n = int(dur * SR); x = rng.uniform(-1, 1, n)
    if hp: x = x - lowpass(x, 5000)
    return x * env(n, 0.001, d)


def clap():
    x = noise(0.2, 0.06, hp=False); x = x - lowpass(x, 900)
    return x * 0.9


def click():
    return noise(0.012, 0.003) * 0.6


def chime(f=880):
    return tone(f, 1.2, 'sine', 0.002, 0.35) + 0.5 * tone(f * 1.5, 1.2, 'sine', 0.002, 0.25) + 0.25 * tone(f * 3.01, 1.2, 'sine', 0.001, 0.1)


def whoosh(t_end, dur=0.35):
    n = int(dur * SR); x = rng.uniform(-1, 1, n); out = np.zeros(n); acc = 0.0
    for i in range(n):
        c = 400 + 7000 * (i / n) ** 2; a = np.exp(-2 * np.pi * c / SR); acc = (1 - a) * x[i] + a * acc; out[i] = acc
    out *= np.sin(np.pi * np.arange(n) / n) ** 2
    add(out, t_end - dur, 0.35)


# --- intro: pad swell, typing, riser, mouse click ---
for f in (220, 261.63, 329.63, 493.88):
    add(tone(f, SC[1] + 0.4, 'sine', 1.6, 3.0), 0.0, 0.05, pan=(f % 3 - 1) * 0.3)
for k in range(27): add(click(), 0.45 + k / 26, 0.5, pan=0.2)
for k in range(26): add(click(), 1.6 + k / 26, 0.5, pan=0.2)
riser = noise(1.1, 2.0); riser *= np.linspace(0, 1, len(riser)) ** 2; add(riser, SC[1] - 1.1, 0.25)
add(noise(0.03, 0.01), 3.05, 0.8)

# --- drums and bass from the drop to the end card ---
drop_start, drop_end = SC[1], SC[6]
bass_roots = [55.0, 43.65, 65.41, 49.0]
b = 0
t = drop_start
while t < drop_end - 1e-6:
    quiet = SC[3] <= t < SC[4]            # leave room for the sonification
    beat = int(round((t - drop_start) / Q))
    add(kick(), t, 0.9 if not quiet else 0.7)
    if beat % 2 == 1: add(clap(), t, 0.45 * (0.5 if quiet else 1))
    add(noise(0.05, 0.02), t + Q / 2, 0.22 * (0.5 if quiet else 1), pan=0.35)
    root = bass_roots[(beat // 4) % 4]
    for e in range(2):
        note = tone(root * (2 if e else 1), Q / 2, 'saw', 0.004, 0.12)
        add(lowpass(note, 380), t + e * Q / 2, 0.55 * (0.6 if quiet else 1))
    t += Q
add(kick(1.3), SC[1], 1.0); add(noise(0.6, 0.25, hp=False), SC[1], 0.25)
for c in SC[2:7]: whoosh(c)

# --- map scene: a tick per acquisition date ---
for k in range(len(D['dates'])):
    add(tone(1760, 0.03, 'square', 0.001, 0.01), SC[2] + 2 * S + k * S, 0.05, pan=-0.3)

# --- pixel card: the sample's own sonification (js/sonify.js mapping) ---
pix, med, sd = D['hv'], D['med'], D['sd']
vals = [v for v in pix + med if v is not None]
lo, hi = min(vals), max(vals) + 0.01
hz = lambda db: 180 * 2 ** (2.5 * min(1, max(0, (db - lo) / (hi - lo))))
for i, (v, m, s_) in enumerate(zip(pix, med, sd)):
    if v is None or m is None or s_ is None or s_ <= 0: continue
    t0 = SC[3] + 2 * S + i * S
    z = min(4, abs(v - m) / s_)
    add(tone(hz(m), S * 0.9, 'sine', 0.01, 0.12), t0, 0.22, pan=-0.5)
    late = z * 0.025 if z > 1.5 else 0
    add(tone(hz(v) * 2, S * 0.85, 'tri', 0.008, 0.11, detune=z * 22 if z > 1.5 else 0), t0 + late, 0.42, pan=0.5)

# --- findings: a boom and a chime per card ---
for i in range(4):
    t0 = SC[4] + Q + i * 2 * Q
    add(kick(1.2), t0, 0.7)
    add(chime([659.25, 783.99, 880.0, 987.77][i]), t0, 0.16)

# --- subsidence: counter roll, strike, stab ---
for k in range(14): add(tone(500 + 60 * k, 0.04, 'square', 0.001, 0.015), SC[5] + 0.5 + k * 0.085, 0.05)
add(noise(0.25, 0.08), SC[5] + 2.0, 0.4, pan=0.3)
for f in (220, 277.18, 329.63): add(tone(f, 0.9, 'saw', 0.004, 0.25), SC[5] + 2.6, 0.06)

# --- end card: chord and the OK ding ---
for f in (110, 220, 261.63, 329.63, 392.0, 493.88):
    add(lowpass(tone(f, 3.2, 'saw', 0.01, 1.4), 1400), SC[6], 0.07)
add(kick(1.3), SC[6], 0.9)
add(chime(1046.5), SC[6] + 2.15, 0.18)

# --- master: fade, soft clip, normalise ---
fade = np.ones(N); k = int(0.6 * SR); fade[-k:] = np.linspace(1, 0, k)
mix = np.stack([L, R], 1) * fade[:, None]
mix = np.tanh(1.3 * mix / np.max(np.abs(mix))) / np.tanh(1.3)
mix *= 0.89 / np.max(np.abs(mix))
with wave.open('soundtrack.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
print('seconds', N / SR)
