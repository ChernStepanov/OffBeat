// Continuous, streamed DEM map. Radar coverage never limits terrain navigation.
window.OB = window.OB || {};
OB.createTerrainRenderer = async function (canvas) {
  const T = await import('./vendor/three.module.min.js'), tiles = OB.terrainTiles;
  const renderer = new T.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); renderer.setClearColor(0x101410);
  renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = .95;
  const scene = new T.Scene(); scene.fog = new T.FogExp2(0x101410, .065);
  const camera = new T.PerspectiveCamera(39, 1, .02, 60);
  scene.add(new T.HemisphereLight(0xe3e2b7, 0x263027, 1.5));
  const light = new T.DirectionalLight(0xffedce, 2); light.position.set(-2, 5, 2); scene.add(light);
  const surface = new T.Group(), overlay = new T.Group(), labels = new T.Group(); scene.add(surface, overlay, labels);
  let center = tiles.mercator(-67.08, 10.47), viewZoom = 12.23, yaw = -.65, pitch = .77, plan = false, ground = false, groundTilt = -.08;
  let exaggeration = 4, mode = 'topo', pointsVisible = true, width = 1, height = 1, targetHeight = 0;
  let site = null, context = null, date = 0, channel = 'hv', selectedIndex = -1, radar = null, marker = null, sampleList = [];
  let coverageDirty = true, overlayDirty = true, paused = false, sourceLevel = 0, wantedKey = '', segments = 64;
  let minHeight = 0, maxHeight = 3000, vertices = 0, nodes = new Map(), desired = [];
  let geometryRevision = 0;
  const target = new T.Vector3(), ray = new T.Raycaster(), screenPointer = new T.Vector2();
  const rampLow = { value: 0 }, rampHigh = { value: 3000 }, contours = { value: 1 };
  const palette = ['#536c68', '#789080', '#a4aa8a', '#c2bd9f', '#d6d2bd', '#eeeade'].map(hex => new T.Color(hex).toArray().map(v => v.toFixed(6)).join(','));
  function terrainShader(shader) {
    shader.uniforms.heightLow = rampLow; shader.uniforms.heightHigh = rampHigh; shader.uniforms.showContours = contours;
    shader.vertexShader = 'attribute float elevation; varying float vElevation;\n' + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvElevation = elevation;');
    shader.fragmentShader = 'uniform float heightLow; uniform float heightHigh; uniform float showContours; varying float vElevation;\n' + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>
      float t = clamp((vElevation-heightLow)/max(1.0,heightHigh-heightLow),0.0,1.0)*5.0;
      vec3 colors[6]; ${palette.map((c, i) => `colors[${i}]=vec3(${c});`).join(' ')}
      int k = min(4,int(floor(t))); vec3 terrainColor = mix(colors[k],colors[k+1],fract(t));
      if(t>=5.0) terrainColor=colors[5];
      if(vElevation<0.0) terrainColor=mix(vec3(0.025,0.065,0.063),vec3(0.008,0.018,0.021),clamp(-vElevation/7000.0,0.0,1.0));
      float interval=max(10.0,floor((heightHigh-heightLow)/200.0)*10.0);
      float coord=vElevation/interval; float edge=abs(fract(coord+0.5)-0.5);
      float ink=1.0-smoothstep(0.0,max(fwidth(coord)*0.9,0.008),edge);
      diffuseColor.rgb=terrainColor*(1.0-ink*showContours*0.22);
    `);
  }
  const landMaterial = new T.MeshStandardMaterial({ roughness: 1, flatShading: true, side: T.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }); landMaterial.onBeforeCompile = terrainShader;
  const cloudMaterial = new T.PointsMaterial({ size: 2, sizeAttenuation: false, transparent: true, opacity: .9, depthWrite: false }); cloudMaterial.onBeforeCompile = terrainShader;
  const signalMaterial = new T.PointsMaterial({ vertexColors: true, size: 4, sizeAttenuation: false, toneMapped: false });
  const scale = () => 2 * 2 ** viewZoom;
  const notify = () => canvas.dispatchEvent(new Event('ob:terrain-stream'));
  const stream = tiles.create(event => {
    if (event.ready) {
      for (const node of nodes.values()) {
        const delta = node.tile.z - event.tile.z;
        if (delta >= 0 && tiles.wrap(Math.floor(node.tile.x / 2 ** delta), 2 ** event.tile.z) === tiles.wrap(event.tile.x, 2 ** event.tile.z) && Math.floor(node.tile.y / 2 ** delta) === event.tile.y) node.dirty = true;
      }
      overlayDirty = true;
    }
    notify();
  });
  // The map is an independent geographic context layer; DEM tiles still determine height.
  const topoStream = tiles.create(event => {
    if (event.ready) {
      const entry = topoStream.cache.get(event.tile.key);
      if (entry) { entry.texture = new T.Texture(entry.bitmap); entry.texture.colorSpace = T.SRGBColorSpace; entry.texture.flipY = false; entry.texture.needsUpdate = true; }
    }
    notify();
  }, {
    limit: 96, concurrency: 5, rootUrl: null,
    decodeImage: async blob => ({ bitmap: await createImageBitmap(blob, { imageOrientation: 'flipY' }) }),
    onEvict: entry => { entry?.texture?.dispose(); entry?.bitmap?.close(); },
  });
  const topoDescriptor = tile => ({ ...tile, url: `https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/${tile.z}/${tile.y}/${tiles.wrap(tile.x, 2 ** tile.z)}` });
  const disposeNode = node => { node.mesh.geometry.dispose(); node.cloud.geometry.dispose(); node.mapMaterial.dispose(); surface.remove(node.group); };
  function location() { return tiles.geographic(center.x, center.y); }
  function elevationAt(lon, lat) {
    const p = tiles.mercator(lon, lat), measured = stream.heightAt(p.x, p.y, 14);
    const prepared = context ? OB.terrain.heightAt(context, lon, lat) : null;
    // Zooming out must not replace a known sample elevation with a coarse world estimate.
    if (measured && (measured.level >= 13 || !Number.isFinite(prepared))) return measured.height_m;
    return Number.isFinite(prepared) ? prepared : measured?.height_m ?? null;
  }
  function localPosition(lon, lat, altitude = null) {
    const p = tiles.mercator(lon, lat), s = scale();
    p.x += Math.round(center.x - p.x);
    const h = altitude ?? elevationAt(lon, lat);
    if (!Number.isFinite(h)) return null;
    return new T.Vector3((p.x - center.x) * s, h / (tiles.C * Math.cos(lat * Math.PI / 180)) * s * exaggeration, (p.y - center.y) * s);
  }
  function updateCamera() {
    const geo = location(), h = elevationAt(geo.lon, geo.lat);
    const previousHeight = targetHeight;
    targetHeight = Number.isFinite(h) ? h / (tiles.C * Math.cos(geo.lat * Math.PI / 180)) * scale() * exaggeration : 0;
    if (Math.abs(previousHeight - targetHeight) > .15) coverageDirty = true;
    if (ground) {
      // An illustrative near-ground view of the DEM, not a surveyed observer position.
      const eyeHeight = Math.max(.015, 20 / (tiles.C * Math.cos(geo.lat * Math.PI / 180)) * scale() * exaggeration);
      camera.position.set(0, targetHeight + eyeHeight, 0);
      target.set(2 * Math.sin(yaw), camera.position.y + 2 * Math.tan(groundTilt), -2 * Math.cos(yaw));
    } else {
      target.set(0, targetHeight, 0);
      const angle = plan ? Math.PI / 2 - .001 : pitch, distance = 3.95 * Math.max(1, 1.15 / camera.aspect);
      camera.position.set(distance * Math.cos(angle) * Math.sin(yaw), targetHeight + distance * Math.sin(angle), distance * Math.cos(angle) * Math.cos(yaw));
    }
    camera.up.set(0, 1, 0); camera.lookAt(target); camera.updateMatrixWorld();
  }
  function updateCoverage() {
    desired = tiles.orbitCoverage(center, viewZoom); sourceLevel = desired[0]?.z || 0;
    segments = 64;
    const keys = desired.map(t => t.meshKey).join('|') + '/' + segments;
    if (keys !== wantedKey) {
      wantedKey = keys;
      const parents = new Map();
      for (const t of desired) {
        const z = Math.max(0, t.z - 2), shift = 2 ** (t.z - z), p = tiles.descriptor(z, Math.floor(t.x / shift), Math.floor(t.y / shift)); parents.set(p.key, p);
      }
      stream.setWanted([tiles.descriptor(0, 0, 0), ...parents.values(), ...desired]);
      topoStream.setWanted(mode === 'topo' ? desired.map(topoDescriptor) : []);
      overlayDirty = true;
    }
    coverageDirty = false;
  }
  function buildTile(tile) {
    if (!stream.cache.has('0/0/0')) return false;
    const count = segments + 1, n = 2 ** tile.z, positions = new Float32Array(count * count * 3), elevations = new Float32Array(count * count), uvs = new Float32Array(count * count * 2);
    let low = Infinity, high = -Infinity, detail = 14;
    for (let row = 0; row < count; row++) for (let col = 0; col < count; col++) {
      const i = row * count + col, x = (tile.x + col / segments) / n, y = Math.min(1 - 1e-12, (tile.y + row / segments) / n);
      const measured = stream.heightAt(x, y, tile.z); if (!measured) return false;
      const h = measured.height_m, cosine = Math.cosh(Math.PI * (1 - 2 * y));
      positions.set([col / segments, h * cosine, row / segments], i * 3); elevations[i] = h; uvs.set([col / segments, 1 - row / segments], i * 2);
      low = Math.min(low, h); high = Math.max(high, h); detail = Math.min(detail, measured.level);
    }
    const geometry = new T.BufferGeometry(); geometry.setAttribute('position', new T.BufferAttribute(positions, 3)); geometry.setAttribute('elevation', new T.BufferAttribute(elevations, 1)); geometry.setAttribute('uv', new T.BufferAttribute(uvs, 2));
    const indices = [];
    for (let y = 0; y < segments; y++) for (let x = 0; x < segments; x++) { const a = y * count + x; indices.push(a, a + count, a + 1, a + 1, a + count, a + count + 1); }
    geometry.setIndex(indices); geometry.computeVertexNormals(); geometry.computeBoundingBox();
    const cloudGeometry = new T.BufferGeometry(); cloudGeometry.setAttribute('position', geometry.getAttribute('position')); cloudGeometry.setAttribute('elevation', geometry.getAttribute('elevation'));
    const mapMaterial = new T.MeshStandardMaterial({ roughness: 1, side: T.DoubleSide, toneMapped: false });
    const group = new T.Group(), mesh = new T.Mesh(geometry, landMaterial), cloud = new T.Points(cloudGeometry, cloudMaterial);
    mesh.frustumCulled = cloud.frustumCulled = false; group.add(mesh, cloud);
    const previous = nodes.get(tile.meshKey); if (previous) disposeNode(previous);
    surface.add(group); nodes.set(tile.meshKey, { group, mesh, cloud, mapMaterial, tile, low, high, detail, segments, dirty: false });
    geometryRevision++;
    return true;
  }
  function positionTiles() {
    const s = scale(); minHeight = Infinity; maxHeight = -Infinity; vertices = 0;
    for (const node of nodes.values()) {
      const n = 2 ** node.tile.z;
      node.group.position.set((node.tile.x / n - center.x) * s, 0, (node.tile.y / n - center.y) * s);
      node.group.scale.set(s / n, s / tiles.C * exaggeration, s / n);
      const tex = mode === 'topo' ? topoStream.cache.get(node.tile.key)?.texture : null;
      if (tex && node.mapMaterial.map !== tex) { node.mapMaterial.map = tex; node.mapMaterial.needsUpdate = true; }
      node.mesh.material = tex ? node.mapMaterial : landMaterial;
      node.mesh.visible = mode !== 'points'; node.cloud.visible = mode === 'points' || mode === 'hybrid';
      minHeight = Math.min(minHeight, node.low); maxHeight = Math.max(maxHeight, node.high); vertices += (node.segments + 1) ** 2;
    }
    if (!nodes.size) { minHeight = 0; maxHeight = 3000; }
    rampLow.value = Math.max(0, minHeight); rampHigh.value = Math.max(rampLow.value + 100, maxHeight);
  }
  const sitePins = [];
  for (const s of OB.SITES) {
    const cv = document.createElement('canvas'); cv.width = 240; cv.height = 28;
    const ctx = cv.getContext('2d'); ctx.font = '12.5px W95FA, Tahoma, sans-serif';
    const name = s.name, labelWidth = Math.min(230, Math.ceil(ctx.measureText(name).width) + 23);
    ctx.fillStyle = '#151b15'; ctx.fillRect(0, 1, labelWidth, 24); ctx.strokeStyle = '#aaa98a'; ctx.strokeRect(.5, 1.5, labelWidth - 1, 23);
    ctx.fillStyle = '#dbb47a'; ctx.fillRect(6, 10, 6, 6); ctx.fillStyle = '#e4ddbd'; ctx.fillText(name, 18, 17);
    const texture = new T.CanvasTexture(cv); texture.colorSpace = T.SRGBColorSpace;
    const sprite = new T.Sprite(new T.SpriteMaterial({ map: texture, depthTest: false, toneMapped: false, transparent: true })); sprite.center.set(0, .5); sprite.renderOrder = 20;
    labels.add(sprite); sitePins.push({ site: s, sprite, width: labelWidth });
  }
  function positionPins() {
    const unit = camera.position.distanceTo(target) * Math.tan(camera.fov * Math.PI / 360) * 2 / height;
    for (const pin of sitePins) {
      const p = localPosition(pin.site.center[1], pin.site.center[0], 0);
      pin.sprite.position.copy(p); pin.sprite.position.y += .002;
      pin.sprite.scale.set(240 * unit, 28 * unit, 1); pin.sprite.visible = viewZoom < 10;
    }
  }
  function rebuildSamples() {
    if (radar) { radar.geometry.dispose(); overlay.remove(radar); radar = null; }
    sampleList = [];
    if (site?.dates[date]) site.pixels.forEach((p, index) => {
      const value = p[channel]?.[date]; if (!Number.isFinite(value) || ![p.lat, p.lon].every(Number.isFinite)) return;
      const height_m = elevationAt(p.lon, p.lat), position = localPosition(p.lon, p.lat, height_m); if (!position) return;
      position.y += .003;
      sampleList.push({ index, value, position, height_m, lat: p.lat, lon: p.lon });
    });
    if (sampleList.length) {
      const positions = [], colors = [];
      for (const p of sampleList) { positions.push(...p.position.toArray()); const c = new T.Color(`rgb(${OB.pointCloud.color(p.value).join(',')})`); colors.push(...c.toArray()); }
      const geometry = new T.BufferGeometry(); geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3)); geometry.setAttribute('color', new T.Float32BufferAttribute(colors, 3));
      radar = new T.Points(geometry, signalMaterial); radar.frustumCulled = false; radar.visible = pointsVisible && viewZoom >= 9; overlay.add(radar);
    }
    setSelection(selectedIndex); overlayDirty = false;
  }
  function setSelection(index) {
    selectedIndex = index;
    if (marker) { marker.geometry.dispose(); marker.material.dispose(); overlay.remove(marker); marker = null; }
    const p = sampleList.find(p => p.index === index); if (!p || !pointsVisible || viewZoom < 9) return;
    marker = new T.Mesh(new T.RingGeometry(.018, .025, 24), new T.MeshBasicMaterial({ color: 0xffe5a4, side: T.DoubleSide, depthTest: false, toneMapped: false }));
    marker.position.copy(p.position); marker.renderOrder = 15; overlay.add(marker);
  }
  function render() {
    if (paused) return;
    const rect = canvas.getBoundingClientRect(); if (rect.width < 1 || rect.height < 1) return;
    const w = Math.round(rect.width), h = Math.round(rect.height);
    if (w !== width || h !== height) { width = w; height = h; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); coverageDirty = true; }
    updateCamera(); if (coverageDirty) updateCoverage();
    let built = 0;
    for (const tile of desired) {
      const node = nodes.get(tile.meshKey);
      if ((!node || node.dirty || node.segments !== segments) && buildTile(tile)) { if (++built >= 3) break; }
    }
    const pendingMeshes = desired.some(t => { const n = nodes.get(t.meshKey); return !n || n.dirty || n.segments !== segments; });
    if (!pendingMeshes) {
      const keep = new Set(desired.map(t => t.meshKey));
      for (const [key, node] of nodes) if (!keep.has(key)) { disposeNode(node); nodes.delete(key); }
    }
    positionTiles(); if (overlayDirty || built) rebuildSamples();
    positionPins();
    if (marker) {
      marker.quaternion.copy(camera.quaternion);
      const unit = camera.position.distanceTo(marker.position) * Math.tan(camera.fov * Math.PI / 360) * 2 / height;
      marker.scale.setScalar(unit * 10 / .025);
    }
    renderer.render(scene, camera);
    if (built && pendingMeshes) notify();
  }
  function pick(x, y) {
    for (const pin of sitePins) if (pin.sprite.visible) {
      const p = pin.sprite.position.clone().project(camera), px = (p.x + 1) * width / 2, py = (1 - p.y) * height / 2;
      if (p.z > -1 && p.z < 1 && x >= px && x <= px + pin.width && Math.abs(y - py) < 14) return { kind: 'site', siteId: pin.site.id };
    }
    if (!radar?.visible) return null;
    const candidates = sampleList.map(p => { const v = p.position.clone().project(camera); return { p, v, x: (v.x + 1) * width / 2, y: (1 - v.y) * height / 2 }; })
      .map(p => ({ ...p, gap: Math.hypot(p.x - x, p.y - y) })).filter(p => p.v.z > -1 && p.v.z < 1 && p.gap <= 8).sort((a, b) => a.gap - b.gap);
    for (const candidate of candidates) {
      screenPointer.set(candidate.x / width * 2 - 1, 1 - candidate.y / height * 2); ray.setFromCamera(screenPointer, camera);
      const hit = mode === 'points' ? null : ray.intersectObjects([...nodes.values()].map(n => n.mesh))[0];
      if (!hit || candidate.p.position.distanceTo(camera.position) <= hit.distance + .015) return candidate.p;
    }
    return null;
  }
  function changed() { coverageDirty = true; overlayDirty = true; notify(); }
  function goTo(lon, lat, zoom = viewZoom) {
    if (![lon, lat, zoom].every(Number.isFinite)) return false;
    center = tiles.mercator(tiles.geographic((lon + 180) / 360, .5).lon, tiles.clamp(lat, -tiles.MAX_LAT, tiles.MAX_LAT));
    viewZoom = tiles.clamp(zoom, 0, 19); wantedKey = ''; changed(); return true;
  }
  function focusSite(s) {
    if (!s) return;
    const b = s.grid.bbox, span = Math.max((b.e - b.w) / 360, Math.abs(tiles.mercator(0, b.s).y - tiles.mercator(0, b.n).y)) * 3;
    goTo((b.w + b.e) / 2, (b.n + b.s) / 2, Math.log2(1 / span));
  }
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); canvas.dispatchEvent(new CustomEvent('ob:gpu-status', { detail: 'lost' })); });
  canvas.addEventListener('webglcontextrestored', () => { for (const node of nodes.values()) node.dirty = true; notify(); canvas.dispatchEvent(new CustomEvent('ob:gpu-status', { detail: 'restored' })); });
  return {
    render, pick, goTo, focusSite, elevationAt,
    setTerrain(data, s) { context = data; if (s) site = s; overlayDirty = true; },
    setSamples(s, t, pol) { site = s; date = t; channel = pol; overlayDirty = true; },
    select: setSelection,
    rotate(dx, dy) {
      if (ground) {
        yaw += dx * .007;
        groundTilt = tiles.clamp(groundTilt - dy * .006, -1.48, 1.48);
      } else if (!plan) {
        yaw -= dx * .007;
        pitch = tiles.clamp(pitch + dy * .006, -1.48, 1.48);
      }
      notify();
    },
    pan(dx, dy) { const unit = camera.position.distanceTo(target) / height / scale(); center.x += (-dx * Math.cos(yaw) + dy * Math.sin(yaw)) * unit; center.y += (dx * Math.sin(yaw) + dy * Math.cos(yaw)) * unit; center.x = tiles.wrap(center.x, 1); center.y = tiles.clamp(center.y, 0, 1); changed(); },
    walk(forward, right) {
      if (!ground || !Number.isFinite(forward) || !Number.isFinite(right)) return;
      const unit = .16 / scale();
      center.x = tiles.wrap(center.x + (Math.sin(yaw) * forward + Math.cos(yaw) * right) * unit, 1);
      center.y = tiles.clamp(center.y + (-Math.cos(yaw) * forward + Math.sin(yaw) * right) * unit, 0, 1);
      changed();
    },
    zoom(factor) { if (Number.isFinite(factor) && factor > 0) { viewZoom = tiles.clamp(viewZoom + Math.log2(factor), 0, 19); changed(); } },
    setView(view) { plan = view === 'plan'; ground = view === 'ground'; yaw = plan ? 0 : -.65; pitch = .77; groundTilt = -.08; notify(); },
    setExaggeration(value) { exaggeration = value; overlayDirty = true; notify(); },
    setMode(value) { mode = value; wantedKey = ''; coverageDirty = true; notify(); }, setContours(value) { contours.value = value ? 1 : 0; notify(); },
    setPointsVisible(value) { pointsVisible = value; overlayDirty = true; notify(); },
    retry: () => { stream.retry(); topoStream.retry(); },
    setActive(value) { paused = !value; if (value) { stream.resume(); topoStream.resume(); changed(); } else { stream.stop(); topoStream.stop(); } },
    projectSample(index) { const p = sampleList.find(p => p.index === index); if (!p) return null; const v = p.position.clone().project(camera); return { x: (v.x + 1) * width / 2, y: (1 - v.y) * height / 2, depth: v.z }; },
    info: () => {
      const network = stream.info(), topo = topoStream.info(), building = desired.filter(t => { const n = nodes.get(t.meshKey); return !n || n.dirty || n.segments !== segments; }).length;
      return { geometryRevision, terrainVertices: vertices, terrainTiles: nodes.size, desiredTiles: desired.length, fineTiles: desired.filter(t => stream.cache.has(t.key)).length,
        radarSamples: sampleList.length, exaggeration, mode, view: ground ? 'ground' : plan ? 'plan' : 'orbit', groundTilt, renderer: 'WebGL / Three.js', yaw, pitch, zoom: viewZoom, sourceLevel, center: location(),
        mapPending: mode === 'topo' ? topo.pending : 0, mapFailed: mode === 'topo' ? topo.failed : 0, mapReady: mode === 'topo' ? desired.filter(t => topoStream.cache.has(t.key)).length : 0,
        min_m: minHeight, max_m: maxHeight, span_m: tiles.C * Math.cos(location().lat * Math.PI / 180) / 2 ** viewZoom,
        ...network, building, loading: coverageDirty || network.pending > 0 || building > 0 };
    },
  };
};
