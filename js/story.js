// Guided tour: a Win98-style wizard that drives the map one chapter at a time.
// Chapters pick their pixel by a rule ("largest clearing", "fastest sinking"), never by fixed
// coordinates, so they keep working when the data behind them is replaced.
window.OB = window.OB || {};

(function () {
  const $ = id => document.getElementById(id);
  const hash = location.hash.slice(1);
  OB.tourWanted = hash === "" || hash === "tour" || hash.startsWith("tour/");
  const startAt = hash.startsWith("tour/") ? Math.max(0, parseInt(hash.slice(5), 10) - 1 || 0) : 0;

  const fmtDate = d => new Date(d + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const synthetic = s => /synthetic/i.test(s.source || "");

  // ---- pixel rules -------------------------------------------------------
  const largestPatch = style => app => {
    const p = OB.app.patches().find(q => q.style === style);
    return p ? p.peak : null;
  };
  const extreme = (layer, sign) => () => {
    const a = OB.app.site().grid.extra && OB.app.site().grid.extra[layer];
    if (!a) return null;
    let best = null, bv = -Infinity;
    for (let i = 0; i < a.length; i++) { const v = sign * a[i]; if (Number.isFinite(v) && v > bv) { bv = v; best = i; } }
    return best;
  };
  const measuredSample = () => {
    const s = OB.app.site();
    if (!s.pixels) return null;
    // an accepted built-up sample, nearest the middle of the case area
    const n = s.grid.n, mid = (n - 1) / 2;
    let best = null, bd = Infinity;
    s.pixels.forEach((p, i) => {
      if (!(p.disp && p.hv.every(Number.isFinite) && p.cover === 50)) return;
      const d = Math.hypot(i % n - mid, Math.floor(i / n) - mid);
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  };

  // fires within 1 km and 60 days of the pixel's change date
  function firesNear(site, p) {
    const f = site.context && site.context.fires;
    if (!f || !p.since) return null;
    const t = Date.parse(p.since), k = Math.cos(p.lat * Math.PI / 180);
    return f.filter(x => Math.abs(Date.parse(x.date) - t) <= 60 * 864e5 &&
      Math.hypot((x.lat - p.lat) * 111.32, (x.lon - p.lon) * 111.32 * k) <= 1).length;
  }

  // ---- chapters ----------------------------------------------------------
  const CHAPTERS = [
    {
      step: "Radar through cloud",
      site: "mexico", layers: { offbeat: true }, pick: measuredSample,
      title: "Radar sees what cameras miss",
      text: (s, p) => `<p>This is real NISAR data: L-band radar over Mexico City's airport, ${fmtDate(s.dates[s.dates.length - 1])}.
        Red is strong HV backscatter from buildings and rough ground; blue is the smooth runways.</p>
        <p>Radar brings its own light, so it sees the same at night and through cloud. The hard part is reading it.</p>`
    },
    {
      step: "Neighbours, not the past",
      site: "mexico", layers: { offbeat: false, cover: true }, pick: measuredSample,
      title: "Compare a pixel with its neighbours",
      text: (s, p) => `<p>NISAR has only months of history, too short to compare a pixel with its own past.
        OffBeat compares it with its neighbours instead: pixels of the same land cover nearby (ESA WorldCover).</p>
        <p>The grey band in the plot below is those neighbours. Rain and seasons move the whole band;
        a pixel that leaves it on its own is out of step.</p>`
    },
    {
      step: "A sinking city",
      site: "mexico-full", layers: { offbeat: false, extra: ["up"] }, pick: extreme("up", -1), z: 2.5,
      title: "Mexico City is sinking",
      text: (s, p) => `<p>Pumping water from the old lake bed makes the ground subside. Two orbits, one looking east and one west,
        split the radar's line of sight into vertical and east-west motion.</p>
        <p>The pixel in the yellow box moves <b>${p.extra && Number.isFinite(p.extra.up) ? p.extra.up.toFixed(1) + " cm a year" : "-"}</b> vertically.</p>`
    },
    {
      step: "Forest cleared",
      site: "amazon", layers: { offbeat: true, extra: ["fires", "alerts"] }, pick: largestPatch("drop"), z: 2.5, zoom: 13,
      title: "Forest cleared in the dry season",
      text: (s, p) => {
        const n = firesNear(s, p);
        return `<p>When a forest is cut, HV falls by several decibels: the radar stops bouncing around inside the canopy.
          OffBeat marks the HV drop in red and dates it.</p>
          <p>This pixel fell out of step on <b>${p.since ? fmtDate(p.since) : "-"}</b>.
          ${n == null ? "" : `NASA FIRMS and INPE saw <b>${n}</b> fire${n === 1 ? "" : "s"} within 1 km in the 60 days around it.`}
          Yellow outlines are INPE DETER and UMD GLAD clearing alerts.</p>`;
      }
    },
    {
      step: "Earthquake damage",
      site: "venezuela", layers: { offbeat: false, extra: ["damage"] }, pick: extreme("damage", 1), zoom: 14,
      title: "Where the quake broke buildings",
      text: (s, p) => `<p>An M7.5 earthquake struck off Caracas on 24 June 2026.
        ${s.damagePair ? `NISAR passed on ${fmtDate(s.damagePair[0])} and again on ${fmtDate(s.damagePair[1])}.` : ""}
        Where buildings collapse or shift, the radar echo stops matching from one pass to the next: coherence drops.</p>
        <p>Yellow to red marks built-up pixels that lost more coherence than the rest of the city.
        This one scores <b>${p.extra && Number.isFinite(p.extra.damage) ? "z " + p.extra.damage.toFixed(1) : "-"}</b>.</p>`
    },
    {
      step: "Listen to it",
      site: "amazon", layers: { offbeat: true }, pick: largestPatch("drop"), z: 2.5, sound: true,
      title: "Hear the pixel fall out of step",
      text: () => `<p>Every NISAR pass is one beat. The neighbours keep time; the pixel plays its own curve.
        While it follows the band you hear one chord. When the forest goes, its note drops, comes late and goes sour.</p>
        <p>Press <b>Play the pixel</b>.</p>`
    },
    {
      step: "Your turn",
      site: null, layers: null, pick: null,
      title: "Your turn",
      text: () => `<p>Pick a site on the left, click any pixel on the map, move the threshold, switch layers.
        Every pixel has its own card, plot and sound.</p>
        <p>Open this tour again from the menu bar.</p>`
    }
  ];

  // ---- the wizard window -------------------------------------------------
  let at = 0, busy = 0;

  function render(site, pixel) {
    const c = CHAPTERS[at];
    $("tour-steps").innerHTML = CHAPTERS.map((k, i) =>
      `<li${i === at ? ' aria-current="step"' : ""}${i < at ? ' class="done"' : ""}>${k.step}</li>`).join("");
    $("tour-title").textContent = c.title;
    // chapters read the loaded site; until it is there, say so instead of rendering half a sentence
    $("tour-text").innerHTML = (c.site && !(site && pixel)) ? "<p>Loading...</p>" : c.text(site || {}, pixel || {});
    const fake = site && c.site && synthetic(site);
    $("tour-note").hidden = !(site && c.site);
    $("tour-note").className = "tour__note " + (fake ? "tour__note--warn" : "tour__note--ok");
    $("tour-note").textContent = fake
      ? "Pipeline test on synthetic radar over real land cover. Real NISAR results replace this chapter when processed."
      : "Real NISAR measurement.";
    $("tour-play").hidden = !c.sound;
    $("tour-back").disabled = at === 0;
    $("tour-next").textContent = at === CHAPTERS.length - 1 ? "Finish" : "Next >";
    $("tour-count").textContent = `Step ${at + 1} of ${CHAPTERS.length}`;
  }

  function go(i) {
    return step(i).catch(e => {
      console.error("tour step failed", e);
      $("tour-text").innerHTML = `<p>This step could not load: ${e.message}</p>`;
      $("tour-next").disabled = false;
    });
  }

  async function step(i) {
    at = Math.max(0, Math.min(CHAPTERS.length - 1, i));
    const ticket = ++busy, c = CHAPTERS[at];
    history.replaceState(null, "", "#tour/" + (at + 1));
    $("tour-next").disabled = true;
    render(null, null);
    OB.app.stop();
    if (c.site) {
      const id = OB.app.sites().some(s => s.id === c.site) ? c.site : OB.app.sites()[0].id;
      await OB.app.loadSite(id);
      if (ticket !== busy) return;
      if (c.z) OB.app.setZ(c.z);
      OB.app.setLayers(c.layers || {});
      OB.app.fit();
      const i2 = c.pick && c.pick();
      if (i2 != null) await OB.app.pickCell(i2, false);
      const p = OB.app.pixel();
      if (c.zoom && p) OB.app.zoomTo(p.lat, p.lon, c.zoom);
    }
    if (ticket !== busy) return;
    render(OB.app.site(), OB.app.pixel());
    $("tour-next").disabled = false;
  }

  function open(i) {
    OB.tourActive = true;
    $("tour-win").hidden = false;
    go(i);
  }
  function close() {
    OB.tourActive = false;
    busy++;
    $("tour-win").hidden = true;
    const s = OB.app.site();
    if (s) history.replaceState(null, "", "#" + s.id);
  }

  function wire() {
    $("tour-back").addEventListener("click", () => go(at - 1));
    $("tour-next").addEventListener("click", () => at === CHAPTERS.length - 1 ? close() : go(at + 1));
    $("tour-close").addEventListener("click", close);
    $("tour-play").addEventListener("click", () => OB.app.play());
    $("tour-open").addEventListener("click", e => { e.preventDefault(); open(0); $("tour-win").scrollIntoView({ block: "start" }); });
    document.addEventListener("keydown", e => {
      if ($("tour-win").hidden || e.target.closest("input, textarea")) return;
      if (e.key === "ArrowRight" && !$("tour-next").disabled) $("tour-next").click();
      if (e.key === "ArrowLeft" && !$("tour-back").disabled) $("tour-back").click();
    });
    if (OB.tourWanted) open(startAt);
  }

  // app.js loads its data asynchronously and announces itself when ready
  if (OB.app) wire(); else document.addEventListener("ob:ready", wire, { once: true });
})();
