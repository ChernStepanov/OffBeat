// Guided tour: a Win98-style wizard that drives the map one chapter at a time.
// Chapters pick their pixel by a rule ("largest clearing", "fastest sinking"), never by fixed
// coordinates, so they keep working when the data behind them is replaced.
window.OB = window.OB || {};

(function () {
  const $ = id => document.getElementById(id);
  const hash = location.hash.slice(1);
  OB.tourWanted = hash === "tour" || hash.startsWith("tour/");
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

  // ---- what the data can show ---------------------------------------------
  const siteById = id => OB.app.sites().find(s => s.id === id);
  const has = {
    extra: (id, k) => () => { const s = siteById(id); return !!(s && s.grid.extra && s.grid.extra[k]); },
    style: (id, st) => () => { const s = siteById(id); const c = OB.STYLE_KEYS.indexOf(st);
      return !!(s && s.grid.style.some((v, i) => v === c && Number.isFinite(s.grid.z[i]) && Math.abs(s.grid.z[i]) >= 2.5)); },
    site: id => () => !!siteById(id)
  };
  const median = a => { const b = a.filter(Number.isFinite).sort((x, y) => x - y), n = b.length; return n ? (b[Math.floor((n - 1) / 2)] + b[Math.floor(n / 2)]) / 2 : NaN; };
  // class median of HV per date, then the median over dates: the same measure the C-band comparison uses
  const lastHv = (s, cls) => median(s.dates.map((_, t) => median(s.pixels.filter(p => p.cover === cls).map(p => p.hv[t]))));
  const dispSamples = s => s.pixels.map(p => p.disp && p.disp[p.disp.length - 1]).filter(Number.isFinite);
  const largestMotion = () => {
    const s = OB.app.site(); let best = null, bv = -1;
    s.pixels.forEach((p, i) => { const v = p.disp && Math.abs(p.disp[p.disp.length - 1]); if (Number.isFinite(v) && v > bv) { bv = v; best = i; } });
    return best;
  };
  const classSample = cls => () => {
    const s = OB.app.site(), n = s.grid.n, mid = (n - 1) / 2; let best = null, bd = Infinity;
    s.pixels.forEach((p, i) => { if (p.cover !== cls || !p.hv.every(Number.isFinite)) return;
      const d = Math.hypot(i % n - mid, Math.floor(i / n) - mid); if (d < bd) { bd = d; best = i; } });
    return best;
  };
  const days = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
  // L band against C band on the same points and weeks, when data/<site>/sentinel1.json exists
  const bandGap = s => {
    const g = s.context && s.context.sentinel1 && s.context.sentinel1.summary && s.context.sentinel1.summary.gap_forest_minus_pasture_dB;
    if (!g || !Number.isFinite(g.C_VH)) return "";
    const l = lastHv(s, 10) - lastHv(s, 30);              // the same NISAR gap the paragraph above states
    if (!Number.isFinite(l)) return "";
    return `<p>Sentinel-1 (NASA OPERA RTC, 5.6 cm waves against NISAR's 24 cm) at the same sample locations and roughly the same season puts the
      tree-cover and grassland samples ${Math.abs(g.C_VH).toFixed(1)} dB apart in VH, against ${Math.abs(l).toFixed(1)} dB in NISAR's HV.
      The sensors, acquisition dates and viewing geometries differ; this descriptive comparison does not establish the cause of the difference.</p>`;
  };

  // ---- chapters ------------------------------------------------------------
  // `needs` hides a chapter until the data behind it exists; nothing is shown that was not measured.
  const ALL = [
    {
      step: "Radar through cloud",
      site: "mexico", needs: has.site("mexico"), layers: { offbeat: true }, pick: measuredSample,
      title: "Radar sees what cameras miss",
      text: (s, p) => `<p>This is real NISAR data: L-band radar over Mexico City's airport, ${fmtDate(s.dates[s.dates.length - 1])}.
        Each dot on the left is one measured sample; its HH/HV curves are in the pixel card below. The photo on the right is optical context, or a dated Sentinel-2 image you pick. The map background is not a radar measurement.</p>
        <p>Radar supplies its own illumination and can observe at night and through clouds. Surface moisture, geometry and quality still affect the measurement.</p>`
    },
    {
      step: "Neighbours, not the past",
      site: "mexico", needs: has.site("mexico"), layers: { offbeat: false, cover: true }, pick: measuredSample,
      title: "Compare a pixel with its neighbours",
      text: (s, p) => `<p>This case has ${s.dates.length} radar dates. We compare its own history and sampled neighbours of the same ESA WorldCover 2021 class within 1 km, excluding the sample itself.</p>
        <p>The grey band is the median plus or minus twice the robust spread, when at least 10 valid neighbours exist. It is not a confidence interval. A departure is a candidate for checking; weather and outdated land cover can also explain it.</p>`
    },
    {
      step: "Motion in 12 days",
      site: "mexico", needs: () => { const s = siteById("mexico"); return !!s && dispSamples(s).length > 0; },
      layers: { offbeat: true }, pick: largestMotion,
      title: "One pair of passes, one snapshot of motion",
      text: (s, p) => {
        const d = dispSamples(s), n = s.pixels.length, dd = s.displacement_dates || s.dates;
        const v = p.disp && p.disp[p.disp.length - 1];
        return `<p>Comparing the radar phase of two passes ${days(dd[0], dd[dd.length - 1])} days apart gives line-of-sight motion.
          ${d.length} of ${n} samples here passed the quality checks; they range from
          ${Math.min(...d).toFixed(1)} to +${Math.max(...d).toFixed(1)} cm.</p>
          <p>This sample shows <b>${Number.isFinite(v) ? (v > 0 ? "+" : "") + v.toFixed(2) + " cm" : "-"}</b> of apparent relative LOS change. Ionospheric phase was subtracted; troposphere, tides and reference instability remain possible contributors. One pair cannot separate them or establish a vertical sinking rate.</p>`;
      }
    },
    {
      step: "A sinking city",
      site: "mexico", needs: has.extra("mexico", "up"), layers: { offbeat: false, extra: ["up"] }, pick: extreme("up", -1),
      title: "Mexico City is sinking",
      text: (s, p) => `<p>Pumping water from the old lake bed makes the ground subside. Two orbits, one looking east and one west,
        split the radar's line of sight into vertical and east-west motion.</p>
        <p>The selected sample has an estimated vertical rate of <b>${p.extra && Number.isFinite(p.extra.up) ? p.extra.up.toFixed(1) + " cm a year" : "-"}</b>. This requires compatible ascending and descending time series and an assessed stable reference; northward motion is assumed zero.</p>`
    },
    {
      step: "Tree cover and grassland",
      site: "amazon", needs: has.site("amazon"), layers: { offbeat: true, cover: false }, pick: classSample(10),
      title: "Tree cover and grassland, as radar sees them",
      text: (s, p) => {
        const f = lastHv(s, 10), g = lastHv(s, 30);
        return `<p>Real NISAR over Itupiranga, Pará, ${fmtDate(s.dates[0])} to ${fmtDate(s.dates[s.dates.length - 1])}, at the edge of the Amazon's arc of deforestation.</p>
          <p>Scattering within vegetation can change polarization, producing HV. WorldCover tree-cover samples have a median of <b>${f.toFixed(1)} dB</b> in HV; grassland samples have <b>${g.toFixed(1)} dB</b> over these dates, a ${(f - g).toFixed(1)} dB difference.</p>
          <p>WorldCover is from 2021. Grassland is not proof of pasture, and a radar contrast alone does not establish clearing or biomass.</p>${bandGap(s)}`;
      }
    },
    {
      step: "HV-drop candidate",
      site: "amazon", needs: has.style("amazon", "drop"), layers: { offbeat: true, extra: ["fires", "alerts"] },
      pick: largestPatch("drop"), z: 2.5, zoom: 13,
      title: "An HV-drop candidate to investigate",
      text: (s, p) => {
        const n = firesNear(s, p);
        return `<p>HV has a downward shift relative to sampled neighbours. This curve shape can be consistent with vegetation change, but is not a confirmed clearing or fire.</p>
          <p>This pixel fell out of step on <b>${p.since ? fmtDate(p.since) : "-"}</b>.
          ${n == null ? "" : `NASA FIRMS and INPE saw <b>${n}</b> fire${n === 1 ? "" : "s"} within 1 km in the 60 days around it.`}
          Alert outlines provide dated external context; only a spatial and temporal match counts as supporting evidence. No event area is inferred from these sparse samples.</p>`;
      }
    },
    {
      step: "Caracas, before the quake",
      site: "venezuela", needs: has.site("venezuela"), layers: { offbeat: true, cover: false }, pick: classSample(50),
      title: "Caracas, before the quake",
      text: (s, p) => `<p>Real NISAR over Caracas, ${fmtDate(s.dates[0])} and ${fmtDate(s.dates[s.dates.length - 1])}.
        On 24 June 2026 an M7.5 earthquake struck just off this coast.</p>
        <p>These passes are the city before it: the baseline every later pass is compared against.
        A separately downloaded June 13-25 GUNW subset has no samples passing the current full quality mask. No coseismic displacement or damage has been established here.</p>`
    },
    {
      step: "Earthquake damage",
      site: "venezuela", needs: has.extra("venezuela", "damage"), layers: { offbeat: false, extra: ["damage"] },
      pick: extreme("damage", 1), zoom: 14,
      title: "Coherence-loss candidates",
      text: (s, p) => `<p>Coherence can decrease after structural change, but also with moisture, vegetation, geometry or processing problems. This layer requires comparable pre-event pairs.
        ${s.damagePair ? `NISAR passed on ${fmtDate(s.damagePair[0])} and again on ${fmtDate(s.damagePair[1])}.` : ""}</p>
        <p>Yellow to red marks built-up samples that lost more coherence than the rest of the city; it is a proxy, not a verified building-damage map.
        This one scores <b>${p.extra && Number.isFinite(p.extra.damage) ? "z " + p.extra.damage.toFixed(1) : "-"}</b>.</p>`
    },
    {
      step: "Listen to it",
      site: "amazon", needs: has.style("amazon", "drop"), layers: { offbeat: true }, pick: largestPatch("drop"), z: 2.5, sound: true,
      title: "Hear the pixel fall out of step",
      text: () => `<p>Every NISAR pass is one beat. The neighbours keep time; the pixel plays its own curve.
        A lower measured HV shifts its note; large peer departures delay and detune it. The timing and pitch are a designed mapping, not an independent detector of forest loss.</p><p>Press <b>Play the pixel</b>.</p>`
    },
    {
      step: "Your turn",
      site: null, layers: null, pick: null,
      title: "Your turn",
      text: () => `<p>Pick a site on the left, click any sample on the map, switch layers.
        Every sample has its own card and plot, with its sources one click away.</p>
        <p>Open this tour again from the menu bar.</p>`
    }
  ];
  let CHAPTERS = ALL;

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
    const url = new URL(location.href);
    url.searchParams.delete('lat'); url.searchParams.delete('lon');
    if (c.site) url.searchParams.set('site', c.site);
    url.hash = 'tour/' + (at + 1);
    history.replaceState(null, "", url);
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
    if (s) { const url = new URL(location.href); url.searchParams.set('site', s.id); url.hash = ''; history.replaceState(null, "", url); }
  }

  // First visit with a bare address: a welcome dialog offers the tour instead of starting it unasked.
  function welcome() {
    if (OB.pages && !OB.pages.classic) return; // Workspace home already provides navigation.
    const KEY = "offbeat.welcome.v1", box = $("welcome");
    const params = new URL(location.href).searchParams;
    let seen = false;
    try { seen = localStorage.getItem(KEY) === "seen"; } catch (e) { /* storage off: show it */ }
    if (!box || seen || location.hash || params.has("site") || params.has("lat") || params.get('view') === 'scene') return;
    const close = () => { box.hidden = true; try { localStorage.setItem(KEY, "seen"); } catch (e) { /* ignore */ } document.removeEventListener("keydown", onKey); };
    const onKey = e => { if (e.key === "Escape") close(); };
    $("welcome-tour").addEventListener("click", () => { close(); open(0); $("tour-win").scrollIntoView({ block: "start" }); });
    $("welcome-explore").addEventListener("click", close);
    $("welcome-case").addEventListener("click", () => { close(); OB.evidence.open('amazon-hv-step'); });
    document.addEventListener("keydown", onKey);
    box.hidden = false;
    $("welcome-case").focus();
  }

  function wire() {
    document.addEventListener('ob:manual-navigation', () => { if (OB.tourActive) close(); });
    CHAPTERS = ALL.filter(c => !c.needs || c.needs());
    $("tour-back").addEventListener("click", () => go(at - 1));
    $("tour-next").addEventListener("click", () => at === CHAPTERS.length - 1 ? close() : go(at + 1));
    $("tour-close").addEventListener("click", close);
    $("tour-play").addEventListener("click", () => OB.app.play());
    $("tour-open").addEventListener("click", e => { e.preventDefault(); open(0); $("tour-win").scrollIntoView({ block: "start" }); });
    document.addEventListener("keydown", e => {
      if ($("tour-win").hidden || e.defaultPrevented || e.target.closest('input, textarea, select, button, a, [contenteditable="true"], [role="slider"]')) return;
      if (e.key === "ArrowRight" && !$("tour-next").disabled) $("tour-next").click();
      if (e.key === "ArrowLeft" && !$("tour-back").disabled) $("tour-back").click();
    });
    if (OB.tourWanted) open(startAt);
    // the landing section greets first-time visitors; the welcome box stays for an explicit call
  }

  // app.js loads its data asynchronously and announces itself when ready
  if (OB.app) wire(); else document.addEventListener("ob:ready", wire, { once: true });
})();
