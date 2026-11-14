// Real WebGL terrain, depth-tested point clouds and geographic picking; Three.js is vendored locally.
window.OB = window.OB || {};
OB.createTerrainRenderer = async function (canvas) {
  const T = await import('./vendor/three.module.min.js');
  const model = OB.terrain;
  const renderer = new T.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x101410);
  renderer.outputColorSpace = T.SRGBColorSpace;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .95;
  const scene = new T.Scene();
  scene.fog = new T.FogExp2(0x101410, .075);
  const camera = new T.PerspectiveCamera(39, 1, .02, 50);
  const ambient = new T.HemisphereLight(0xe3e2b7, 0x263027, 1.5);
  const light = new T.DirectionalLight(0xffedce, 2.0); light.position.set(-2, 5, 2);
  scene.add(ambient, light);
  const ground = new T.GridHelper(6, 30, 0x62664d, 0x343c30); ground.position.y = -.14;
  ground.material.transparent = true; ground.material.opacity = .28; scene.add(ground);
  const group = new T.Group(); scene.add(group);
  const raycaster = new T.Raycaster(), mouse = new T.Vector2();
  const target = new T.Vector3(0, .12, 0);
  let yaw = -.65, pitch = .77, distance = 3.95, mode = 'hybrid', exaggeration = 4, plan = false;
  let dem = null, site = null, date = 0, channel = 'hv', mesh = null, terrainPoints = null, radar = null, marker = null, sampleList = [], indices = [];
  let contours = true, pointsVisible = true, selectedIndex = -1, width = 1, height = 1;
  const contourUniform = { value: 1 };
  const vector = p => new T.Vector3(p.x, p.y, p.z);
  const dispose = object => {
    object.traverse(node => { node.geometry?.dispose(); const mats = node.material ? (Array.isArray(node.material) ? node.material : [node.material]) : []; mats.forEach(m => m.dispose()); });
    object.removeFromParent();
  };
  function updateCamera() {
    camera.up.set(0, 1, 0);
    const angle = plan ? Math.PI / 2 - .001 : pitch;
    const fittedDistance = distance * Math.max(1, 1.15 / camera.aspect);
    camera.position.set(target.x + fittedDistance * Math.cos(angle) * Math.sin(yaw), target.y + fittedDistance * Math.sin(angle), target.z + fittedDistance * Math.cos(angle) * Math.cos(yaw));
    camera.lookAt(target); camera.updateMatrixWorld();
  }
  function render() {
    const box = canvas.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return;
    const w = Math.round(box.width), h = Math.round(box.height);
    if (w !== width || h !== height) { width = w; height = h; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
    updateCamera();
    if (marker?.userData.reticle) marker.userData.reticle.quaternion.copy(camera.quaternion);
    renderer.render(scene, camera);
  }
  function buildTerrain() {
    while (group.children.length) dispose(group.children[0]);
    mesh = terrainPoints = radar = marker = null;
    sampleList = []; indices = [];
    if (!dem) return;
    const n = dem.n, geometry = new T.BufferGeometry();
    const positions = new Float32Array(n * n * 3), colors = new Float32Array(n * n * 3), elevations = new Float32Array(n * n);
    const b = dem.bbox;
    for (let row = 0; row < n; row++) for (let col = 0; col < n; col++) {
      const i = row * n + col, p = model.position(dem, b.w + (b.e - b.w) * col / (n - 1), b.n - (b.n - b.s) * row / (n - 1), exaggeration);
      positions.set([p.x, p.y, p.z], i * 3); elevations[i] = dem.height_m[i];
      const rgb = model.color(elevations[i], dem.min_m, dem.max_m), c = new T.Color(`rgb(${rgb.join(',')})`);
      colors.set([c.r, c.g, c.b], i * 3);
    }
    const triangles = [];
    for (let row = 0; row < n - 1; row++) for (let col = 0; col < n - 1; col++) {
      const a = row * n + col, b = a + 1, c = a + n, d = c + 1; triangles.push(a, c, b, b, c, d);
    }
    geometry.setAttribute('position', new T.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new T.BufferAttribute(colors, 3));
    geometry.setAttribute('elevation', new T.BufferAttribute(elevations, 1));
    geometry.setIndex(triangles); geometry.computeVertexNormals();
    const material = new T.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, flatShading: true, side: T.DoubleSide });
    const interval = Math.max(10, Math.round((dem.max_m - dem.min_m) / 12 / 10) * 10);
    material.onBeforeCompile = shader => {
      shader.uniforms.showContours = contourUniform;
      shader.vertexShader = 'attribute float elevation; varying float vElevation;\n' + shader.vertexShader;
      shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvElevation = elevation;');
      shader.fragmentShader = 'uniform float showContours; varying float vElevation;\n' + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>
        float contourCoord = vElevation / ${interval.toFixed(1)};
        float edge = abs(fract(contourCoord + 0.5) - 0.5);
        float ink = 1.0 - smoothstep(0.0, max(fwidth(contourCoord) * 0.9, 0.008), edge);
        diffuseColor.rgb *= 1.0 - ink * showContours * 0.27;
      `);
    };
    mesh = new T.Mesh(geometry, material); group.add(mesh);
    // A solid cutaway edge gives the geographic surface a physical base.
    const perimeter = [];
    for (let i = 0; i < n; i++) perimeter.push(i);
    for (let i = 1; i < n; i++) perimeter.push(i * n + n - 1);
    for (let i = n - 2; i >= 0; i--) perimeter.push((n - 1) * n + i);
    for (let i = n - 2; i > 0; i--) perimeter.push(i * n);
    const sides = [];
    for (let i = 0; i < perimeter.length; i++) {
      const a = perimeter[i] * 3, b = perimeter[(i + 1) % perimeter.length] * 3;
      const p = [positions[a], positions[a + 1], positions[a + 2]], q = [positions[b], positions[b + 1], positions[b + 2]];
      sides.push(...p, p[0], -.12, p[2], ...q, ...q, p[0], -.12, p[2], q[0], -.12, q[2]);
    }
    const skirts = new T.BufferGeometry(); skirts.setAttribute('position', new T.Float32BufferAttribute(sides, 3)); skirts.computeVertexNormals();
    group.add(new T.Mesh(skirts, new T.MeshStandardMaterial({ color: 0x30332a, roughness: 1, side: T.DoubleSide, flatShading: true })));
    const cloudGeometry = new T.BufferGeometry();
    const cloudPositions = positions.slice();
    for (let i = 1; i < cloudPositions.length; i += 3) cloudPositions[i] += .0015;
    cloudGeometry.setAttribute('position', new T.BufferAttribute(cloudPositions, 3));
    cloudGeometry.setAttribute('color', new T.BufferAttribute(colors.slice(), 3));
    terrainPoints = new T.Points(cloudGeometry, new T.PointsMaterial({ vertexColors: true, size: 1.4, sizeAttenuation: false, transparent: true, opacity: .64, depthWrite: false })); group.add(terrainPoints);
    // Geographic coverage boundary of the SAR subset lies on the DEM, not on a flat floor.
    const sb = site.grid.bbox, outline = [];
    const corners = [[sb.w, sb.n], [sb.e, sb.n], [sb.e, sb.s], [sb.w, sb.s], [sb.w, sb.n]];
    for (let edge = 0; edge < 4; edge++) for (let j = 0; j < 65; j++) {
      const t = j / 64, a = corners[edge], b = corners[edge + 1], p = model.position(dem, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, exaggeration);
      outline.push(p.x, p.y + .004, p.z);
    }
    const borderGeometry = new T.BufferGeometry(); borderGeometry.setAttribute('position', new T.Float32BufferAttribute(outline, 3));
    const border = new T.Line(borderGeometry, new T.LineBasicMaterial({ color: 0xe5d898, transparent: true, opacity: .7 })); group.add(border);
    rebuildSamples(); applyMode();
  }
  function rebuildSamples() {
    if (radar) dispose(radar);
    radar = null; sampleList = model.samples(site, date, channel, dem, exaggeration); indices = sampleList.map(p => p.index);
    if (!sampleList.length) { setSelection(selectedIndex); return; }
    const geometry = new T.BufferGeometry(), positions = [], colors = [];
    for (const p of sampleList) {
      positions.push(p.x, p.y, p.z);
      const c = new T.Color(`rgb(${p.color.join(',')})`); colors.push(c.r, c.g, c.b);
    }
    geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3)); geometry.setAttribute('color', new T.Float32BufferAttribute(colors, 3));
    radar = new T.Points(geometry, new T.PointsMaterial({ vertexColors: true, size: 4.5, sizeAttenuation: false, depthTest: true }));
    radar.visible = pointsVisible; group.add(radar); setSelection(selectedIndex);
  }
  function setSelection(index) {
    selectedIndex = index; if (marker) dispose(marker); marker = null;
    const p = sampleList.find(p => p.index === index); if (!p || !pointsVisible) return;
    marker = new T.Group();
    const ring = new T.Mesh(new T.RingGeometry(.019, .025, 24), new T.MeshBasicMaterial({ color: 0xffe5a4, side: T.DoubleSide, depthTest: false, toneMapped: false }));
    ring.position.copy(vector(p)); ring.position.y += .006; ring.renderOrder = 10; marker.userData.reticle = ring; marker.add(ring);
    const pinGeometry = new T.BufferGeometry().setFromPoints([vector(p), new T.Vector3(p.x, p.y + .11, p.z)]);
    const pin = new T.Line(pinGeometry, new T.LineBasicMaterial({ color: 0xffe5a4, depthTest: false, toneMapped: false })); pin.renderOrder = 11; marker.add(pin);
    group.add(marker);
  }
  function applyMode() {
    if (mesh) mesh.visible = mode !== 'points';
    if (terrainPoints) terrainPoints.visible = mode !== 'relief';
    if (mesh) { mesh.material.transparent = false; mesh.material.opacity = 1; }
  }
  function pick(x, y) {
    if (!radar?.visible) return null;
    const candidates = [];
    for (const p of sampleList) {
      const screen = vector(p).project(camera);
      const px = (screen.x + 1) * width / 2, py = (1 - screen.y) * height / 2;
      const gap = Math.hypot(px - x, py - y);
      if (screen.z > -1 && screen.z < 1 && gap <= 8) candidates.push({ point: p, gap, px, py });
    }
    candidates.sort((a, b) => a.gap - b.gap);
    for (const candidate of candidates) {
      mouse.set(candidate.px / width * 2 - 1, 1 - candidate.py / height * 2);
      raycaster.setFromCamera(mouse, camera);
      const surface = mesh?.visible ? raycaster.intersectObject(mesh)[0] : null;
      // Each candidate gets its own ray: a ridge cannot make a hidden sample selectable.
      if (!surface || vector(candidate.point).distanceTo(camera.position) <= surface.distance + .012) return candidate.point;
    }
    return null;
  }
  updateCamera();
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); canvas.dispatchEvent(new CustomEvent('ob:gpu-status', { detail: 'lost' })); });
  canvas.addEventListener('webglcontextrestored', () => { render(); canvas.dispatchEvent(new CustomEvent('ob:gpu-status', { detail: 'restored' })); });
  return {
    render, pick,
    setTerrain(data, selectedSite) { dem = data; site = selectedSite; target.set(0, data ? (data.max_m - model.frame(data).base_m) * model.frame(data).scale * exaggeration * .3 : .1, 0); buildTerrain(); },
    setSamples(s, t, pol) { site = s; date = t; channel = pol; rebuildSamples(); },
    select: setSelection,
    rotate(dx, dy) { yaw -= dx * .007; if (!plan) pitch = Math.max(.18, Math.min(1.45, pitch + dy * .006)); },
    pan(dx, dy) { const scale = camera.position.distanceTo(target) / height; target.x += (-dx * Math.cos(yaw) + dy * Math.sin(yaw)) * scale; target.z += (dx * Math.sin(yaw) + dy * Math.cos(yaw)) * scale; },
    zoom(factor) { distance = Math.max(.7, Math.min(8, distance / factor)); },
    setView(view) { plan = view === 'plan'; yaw = plan ? 0 : -.65; pitch = .77; distance = 3.95; target.x = target.z = 0; },
    setExaggeration(value) { exaggeration = value; if (dem) { target.y = (dem.max_m - model.frame(dem).base_m) * model.frame(dem).scale * exaggeration * .3; buildTerrain(); } },
    setMode(value) { mode = value; applyMode(); },
    setContours(value) { contours = value; contourUniform.value = contours ? 1 : 0; },
    setPointsVisible(value) { pointsVisible = value; if (radar) radar.visible = value; setSelection(selectedIndex); },
    projectSample(index) { const p = sampleList.find(p => p.index === index); if (!p) return null; const v = vector(p).project(camera); return { x: (v.x + 1) * width / 2, y: (1 - v.y) * height / 2, depth: v.z }; },
    info: () => ({ terrainVertices: dem ? dem.n ** 2 : 0, radarSamples: sampleList.length, exaggeration, mode, renderer: 'WebGL / Three.js', yaw, pitch, distance }),
  };
};
