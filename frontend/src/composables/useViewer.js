/**
 * YASTL - Three.js 3D Model Viewer Composable
 *
 * Vue 3 composable wrapping Three.js scene setup, model loading, and cleanup.
 * Provides reactive loading/error state and auto-disposes on component unmount.
 */
import { ref, onUnmounted } from 'vue';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { plyHasFaces } from '../ply.js';

/**
 * Create a new viewer instance scoped to the calling component.
 *
 * @returns {{ viewerLoading: import('vue').Ref<boolean>, viewerError: import('vue').Ref<string|null>, initViewer: Function, loadModel: Function, resetCamera: Function, dispose: Function }}
 */
export function useViewer() {
    /* ---- Reactive state exposed to the component ---- */
    const viewerLoading = ref(false);
    const viewerError = ref(null);
    /** Download/parse progress of the current load, 0..1 (null = unknown). */
    const viewerProgress = ref(null);
    /** Point-to-point measurement result in mm (null when not measuring). */
    const measuredDistanceMm = ref(null);
    /** Original model dimensions in mm (set after model load). */
    const modelDimensions = ref(null);

    /* ---- Internal Three.js state (not reactive) ---- */
    let scene = null;
    let camera = null;
    let renderer = null;
    let controls = null;
    let currentModel = null;
    let animationId = null;
    let container = null;
    let resizeObserver = null;
    let gridHelper = null;

    /* ---- Orientation gizmo (small axis triad drawn in the corner) ---- */
    let gizmoScene = null;
    let gizmoCamera = null;
    const GIZMO_SIZE = 84; // px square in the bottom-left of the viewport
    const _gizmoOffset = new THREE.Vector3();
    const _rendererSize = new THREE.Vector2();

    /** Scale factor applied to the model (mm → scene units). */
    let modelScaleFactor = 0;
    /** Group holding all bed overlay meshes. */
    let bedGroup = null;
    /** Monotonic token: a loader callback whose token is stale must not
     *  insert its parsed object — it belongs to a superseded request. */
    let loadGeneration = 0;

    /** Default material for models that don't carry their own (teal accent).
     *  PBR + the scene's RoomEnvironment IBL gives surface definition that
     *  the previous Phong material lacked under ACES tone mapping. */
    const DEFAULT_MATERIAL = new THREE.MeshStandardMaterial({
        color: 0x2ec4b6,
        roughness: 0.62,
        metalness: 0.0,
        envMapIntensity: 0.5,
        flatShading: false,
        side: THREE.DoubleSide,
    });

    /* ==================================================================
       Internal helpers
       ================================================================== */

    /**
     * Dispose a material and any textures it references.
     * @param {THREE.Material} material
     */
    function disposeMaterial(material) {
        if (!material) return;
        const textureProps = [
            'map', 'alphaMap', 'aoMap', 'bumpMap', 'displacementMap',
            'emissiveMap', 'envMap', 'lightMap', 'metalnessMap',
            'normalMap', 'roughnessMap', 'specularMap',
        ];
        for (const prop of textureProps) {
            const tex = material[prop];
            if (!tex) continue;
            // FBXLoader mints an object URL per embedded image and never revokes
            // it; Texture.dispose() frees GPU state but leaves the blob pinned,
            // so re-opening such a model would accumulate its texture bytes.
            const src = tex.image && tex.image.src;
            if (typeof src === 'string' && src.startsWith('blob:')) {
                URL.revokeObjectURL(src);
            }
            tex.dispose();
        }
        material.dispose();
    }

    /**
     * Check if a vertex color buffer is too dark to be visible on a dark background.
     * Samples up to 100 evenly-spaced vertices and computes average luminance.
     * @param {THREE.BufferAttribute} colorAttr - The geometry's 'color' attribute.
     * @returns {boolean} True if the average color is below the visibility threshold.
     */
    function isVertexColorDark(colorAttr) {
        const count = colorAttr.count;
        if (count === 0) return true;
        const step = Math.max(1, Math.floor(count / 100));
        let totalLum = 0;
        let samples = 0;
        for (let i = 0; i < count; i += step) {
            const r = colorAttr.getX(i);
            const g = colorAttr.getY(i);
            const b = colorAttr.getZ(i);
            // Relative luminance (ITU-R BT.709)
            totalLum += 0.2126 * r + 0.7152 * g + 0.0722 * b;
            samples++;
        }
        const avgLum = totalLum / samples;
        // Threshold: luminance below 0.15 is hard to see on the dark background
        return avgLum < 0.15;
    }

    /**
     * Whether a vertex-color buffer is a single uniform color across the mesh.
     * trimesh exports plain (colorless) meshes as GLB with a uniform vertex
     * color; that isn't a "real" color, so callers treat uniform buffers as
     * material-less and apply the default material.
     * @param {THREE.BufferAttribute} colorAttr
     * @returns {boolean}
     */
    function isVertexColorUniform(colorAttr) {
        const count = colorAttr.count;
        if (count < 2) return true;
        const r0 = colorAttr.getX(0), g0 = colorAttr.getY(0), b0 = colorAttr.getZ(0);
        const step = Math.max(1, Math.floor(count / 200));
        for (let i = step; i < count; i += step) {
            if (Math.abs(colorAttr.getX(i) - r0) > 0.02
                || Math.abs(colorAttr.getY(i) - g0) > 0.02
                || Math.abs(colorAttr.getZ(i) - b0) > 0.02) {
                return false;
            }
        }
        return true;
    }

    /**
     * Remove and dispose the current model from the scene.
     */
    function clearCurrentModel() {
        if (currentModel && scene) {
            // Put displaced materials back first: a render-mode swap holds the
            // originals off-mesh, and the traversal below can only dispose what
            // is currently attached.
            restoreOriginalMaterials();
            scene.remove(currentModel);
            currentModel.traverse((child) => {
                if (child.geometry) child.geometry.dispose();
                if (child.material) {
                    if (Array.isArray(child.material)) {
                        child.material.forEach(disposeMaterial);
                    } else {
                        disposeMaterial(child.material);
                    }
                }
            });
            currentModel = null;
        }
        modelScaleFactor = 0;
        modelDimensions.value = null;
        clipEnabled = false;
        clearMeasure();
        clearBedOverlay();
        requestRender();
    }

    /**
     * Add a loaded 3D object to the scene, centering it on the origin
     * and auto-scaling it to fit a reasonable viewing size.
     * @param {THREE.Object3D} object
     */
    function addModelToScene(object) {
        if (!scene) return;

        const box = new THREE.Box3().setFromObject(object);

        // Guard against empty or degenerate geometry
        if (box.isEmpty()) {
            console.warn('YASTL viewer: model has empty bounding box');
            scene.add(object);
            currentModel = object;
            resetCamera();
            return;
        }

        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());

        // Guard against NaN/Infinity from malformed geometry
        if (!isFinite(center.x) || !isFinite(center.y) || !isFinite(center.z)) {
            console.warn('YASTL viewer: model has invalid bounds (NaN/Infinity)');
            scene.add(object);
            currentModel = object;
            resetCamera();
            return;
        }

        // Store original dimensions (in model units, typically mm)
        modelDimensions.value = { x: size.x, y: size.y, z: size.z };

        // Auto-scale to fit within a normalized size
        const maxDim = Math.max(size.x, size.y, size.z);
        const scale = maxDim > 0 ? 4 / maxDim : 1;
        modelScaleFactor = scale;

        // Apply scale + position in one shot (object is fresh, at identity),
        // so we don't need a second setFromObject over every vertex:
        //   worldV = scale*localV + position
        // Solve for XZ-centered, bottom on the grid (y=0).
        object.scale.setScalar(scale);
        object.position.set(-scale * center.x, -scale * box.min.y, -scale * center.z);

        scene.add(object);
        currentModel = object;

        // Position camera to see the model
        resetCamera();
        requestRender();
    }

    /* ==================================================================
       Theme
       ================================================================== */

    /** Theme color presets. */
    const THEME_COLORS = {
        default: { bg: 0x12182a, gridCenter: 0x2a3a5c, gridLines: 0x1e2a40 },
        light:   { bg: 0xf5f5f5, gridCenter: 0xcccccc, gridLines: 0xdddddd },
    };

    /**
     * Update scene background and grid colors to match the app theme.
     * @param {'default'|'light'} theme
     */
    function setViewerTheme(theme) {
        const colors = THEME_COLORS[theme] || THEME_COLORS.default;
        if (scene) {
            scene.background = new THREE.Color(colors.bg);
        }
        if (gridHelper) {
            gridHelper.material.color.setHex(colors.gridLines);
            if (gridHelper.material.uniforms) {
                // GridHelper uses a single material; centerLine color is baked
                // into the geometry colors — replace the helper entirely.
            }
            // GridHelper stores center-line colour in geometry vertex colors.
            // Cheapest fix: remove old grid and add a new one.
            if (scene) {
                scene.remove(gridHelper);
                gridHelper.geometry.dispose();
                gridHelper.material.dispose();
                gridHelper = new THREE.GridHelper(20, 40, colors.gridCenter, colors.gridLines);
                gridHelper.material.opacity = 0.6;
                gridHelper.material.transparent = true;
                scene.add(gridHelper);
            }
        }
        requestRender();
    }

    /* ==================================================================
       Public API
       ================================================================== */

    /**
     * Initialize the Three.js scene, camera, renderer, controls, lights, and grid
     * inside the given container element.
     *
     * @param {string} containerId - The id of the DOM element to render into.
     * @param {'default'|'light'} [theme='default'] - Color theme for the scene.
     */
    /**
     * Build a small canvas-texture sprite label (e.g. "X") in the given color,
     * placed at `pos`. Sprites always face the camera so the letter stays legible.
     */
    function makeAxisLabel(text, color, pos) {
        const c = document.createElement('canvas');
        c.width = 64;
        c.height = 64;
        const ctx = c.getContext('2d');
        ctx.fillStyle = color;
        ctx.font = 'bold 48px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 32, 34);
        const tex = new THREE.CanvasTexture(c);
        tex.colorSpace = THREE.SRGBColorSpace;
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
        sprite.position.copy(pos);
        sprite.scale.set(0.6, 0.6, 0.6);
        return sprite;
    }

    /**
     * Create the orientation-gizmo scene: a colored axis triad (X red, Y green,
     * Z blue) with letter labels, rendered in the viewport corner and synced to
     * the main camera's orientation each frame.
     */
    function buildGizmo() {
        gizmoScene = new THREE.Scene();
        const axes = new THREE.AxesHelper(1.3);
        // AxesHelper is unlit; make sure it ignores depth so labels/lines read cleanly.
        axes.material.depthTest = false;
        axes.material.toneMapped = false;
        gizmoScene.add(axes);
        gizmoScene.add(makeAxisLabel('X', '#e06c75', new THREE.Vector3(1.7, 0, 0)));
        gizmoScene.add(makeAxisLabel('Y', '#98c379', new THREE.Vector3(0, 1.7, 0)));
        gizmoScene.add(makeAxisLabel('Z', '#61afef', new THREE.Vector3(0, 0, 1.7)));
        gizmoCamera = new THREE.OrthographicCamera(-2, 2, 2, -2, 0.1, 100);
        gizmoCamera.position.set(0, 0, 5);
    }

    /**
     * Draw the gizmo in the bottom-left corner, oriented to match the main view.
     * Called after the main scene render while autoClear is disabled.
     */
    function renderGizmo() {
        if (!gizmoScene || !camera || !controls) return;
        // Point the gizmo camera along the same direction as the main camera
        // (relative to its orbit target), at a fixed distance from the origin.
        _gizmoOffset.copy(camera.position).sub(controls.target);
        if (_gizmoOffset.lengthSq() === 0) return;
        _gizmoOffset.setLength(5);
        gizmoCamera.position.copy(_gizmoOffset);
        gizmoCamera.up.copy(camera.up);
        gizmoCamera.lookAt(0, 0, 0);

        renderer.getSize(_rendererSize);
        // Top-left corner (WebGL viewport origin is bottom-left, so y is measured
        // from the top). Clear of the bottom toolbar, which spans the full width
        // on mobile.
        const gx = 8;
        const gy = Math.max(8, _rendererSize.y - GIZMO_SIZE - 8);
        renderer.autoClear = false;
        renderer.clearDepth();
        renderer.setScissorTest(true);
        renderer.setViewport(gx, gy, GIZMO_SIZE, GIZMO_SIZE);
        renderer.setScissor(gx, gy, GIZMO_SIZE, GIZMO_SIZE);
        renderer.render(gizmoScene, gizmoCamera);
        renderer.setScissorTest(false);
        renderer.setViewport(0, 0, _rendererSize.x, _rendererSize.y);
        renderer.autoClear = true;
    }

    function initViewer(containerId, theme) {
        if (renderer) {
            // Re-entry without an intervening dispose (e.g. double-click
            // opening a model twice) would stack canvases and rAF loops
            // and leak the previous WebGL context.
            dispose();
        }
        container = document.getElementById(containerId);
        if (!container) {
            console.warn('YASTL viewer: container not found:', containerId);
            return;
        }

        const w = container.clientWidth || 800;
        const h = container.clientHeight || 500;

        // ---- Scene ----
        scene = new THREE.Scene();
        const initColors = THEME_COLORS[theme] || THEME_COLORS.default;
        scene.background = new THREE.Color(initColors.bg);

        // ---- Camera ----
        camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 10000);
        camera.position.set(4, 3, 4);

        // ---- Renderer ----
        renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: false,
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(w, h);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        // Lower exposure so light/white materials don't wash out.
        renderer.toneMappingExposure = 0.82;
        container.appendChild(renderer.domElement);

        // ---- Controls ----
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.screenSpacePanning = true;
        controls.minDistance = 0.1;
        controls.maxDistance = 500;

        // ---- Environment (image-based lighting for the PBR material) ----
        const pmrem = new THREE.PMREMGenerator(renderer);
        scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
        // Dim the IBL — RoomEnvironment is bright and over-lit the models.
        scene.environmentIntensity = 0.5;
        pmrem.dispose();

        // ---- Lights ----
        // Env map carries most of the fill; ambient stays low
        const ambient = new THREE.AmbientLight(0xffffff, 0.15);
        scene.add(ambient);

        // Main directional (key light, casts the ground shadow)
        const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
        keyLight.position.set(5, 10, 7);
        keyLight.castShadow = true;
        keyLight.shadow.mapSize.set(1024, 1024);
        scene.add(keyLight);

        // Secondary directional (fill light, slightly blue)
        const fillLight = new THREE.DirectionalLight(0x8899bb, 0.25);
        fillLight.position.set(-5, 5, -5);
        scene.add(fillLight);

        // ---- Shadow catcher ----
        const shadowGround = new THREE.Mesh(
            new THREE.PlaneGeometry(60, 60),
            new THREE.ShadowMaterial({ opacity: 0.28 })
        );
        shadowGround.rotation.x = -Math.PI / 2;
        shadowGround.position.y = -0.001;
        shadowGround.receiveShadow = true;
        scene.add(shadowGround);

        // ---- Grid ----
        const themeColors = THEME_COLORS[theme] || THEME_COLORS.default;
        gridHelper = new THREE.GridHelper(20, 40, themeColors.gridCenter, themeColors.gridLines);
        gridHelper.material.opacity = 0.6;
        gridHelper.material.transparent = true;
        scene.add(gridHelper);

        // ---- Orientation gizmo ----
        buildGizmo();

        // ---- Resize handling ----
        resizeObserver = new ResizeObserver(() => {
            if (!container || !renderer || !camera) return;
            const cw = container.clientWidth;
            const ch = container.clientHeight;
            if (cw === 0 || ch === 0) return;
            if (camera.isOrthographicCamera) {
                const halfH = (camera.top - camera.bottom) / 2;
                const halfW = halfH * (cw / ch);
                camera.left = -halfW;
                camera.right = halfW;
            } else {
                camera.aspect = cw / ch;
            }
            camera.updateProjectionMatrix();
            renderer.setSize(cw, ch);
            requestRender();
        });
        resizeObserver.observe(container);

        // ---- Render-on-demand ----
        // A continuous rAF loop burned GPU/battery while the viewer sat
        // idle; frames are only scheduled on interaction/state changes,
        // and damping keeps requesting frames until it settles.
        controls.addEventListener('change', requestRender);

        // Measurement point-picking (only acts while measuring is enabled).
        renderer.domElement.addEventListener('pointerdown', onMeasureDown);
        renderer.domElement.addEventListener('pointerup', onMeasureUp);

        requestRender();
    }

    let renderRequested = false;

    function requestRender() {
        if (renderRequested || !renderer) return;
        renderRequested = true;
        animationId = requestAnimationFrame(renderFrame);
    }

    function renderFrame() {
        renderRequested = false;
        animationId = null;
        if (!renderer || !scene || !camera) return;
        const moving = controls ? controls.update() : false;
        renderer.render(scene, camera);
        renderGizmo();
        if (moving) requestRender();
    }

    /**
     * Load a 3D model from a URL into the current scene.
     *
     * Pipeline: fetch the bytes (with progress + a small session cache),
     * parse them (STL/PLY off the main thread in a Web Worker, others on
     * the main thread), then add to the scene. Clears any previous model
     * first and honors the load-generation guard so a superseded load
     * never touches the scene.
     *
     * @param {string} url - URL to fetch the model file.
     * @param {string} format - File format ("stl", "obj", "gltf", "glb", "ply", "3mf").
     * @param {{ onProgress?: (fraction: number) => void, flat?: boolean }} [opts]
     * @returns {Promise<void>}
     */
    // The in-flight download, so opening another model can stop it. Without
    // this, clicking through a few large models leaves every one of their
    // downloads running and competing for the same connection: the previews
    // here are 8-9 MB apiece, so the model actually being looked at can wait a
    // long time behind ones already abandoned.
    let _loadAbort = null;

    async function loadModel(url, format, opts = {}) {
        clearCurrentModel();
        viewerError.value = null;

        if (_loadAbort) _loadAbort.abort();
        const abort = new AbortController();
        _loadAbort = abort;

        const fmt = (format || '').toLowerCase().replace(/^\./, '');
        const gen = ++loadGeneration;
        viewerProgress.value = 0;
        const userProgress = typeof opts.onProgress === 'function' ? opts.onProgress : null;
        const onProgress = (f) => {
            if (gen === loadGeneration) viewerProgress.value = f;
            if (userProgress) userProgress(f);
        };

        try {
            const buffer = await fetchBuffer(url, onProgress, abort.signal);
            if (gen !== loadGeneration) return; // superseded during download

            const object = await parseBuffer(buffer, fmt, opts);
            if (gen !== loadGeneration) {
                disposeObject3D(object);
                return;
            }
            if (scene) {
                addModelToScene(object);
                // Carry the active render mode onto the newly loaded model.
                applyRenderMode();
                requestRender();
            }
            if (gen === loadGeneration) viewerProgress.value = null;
        } catch (err) {
            if (gen !== loadGeneration) return; // superseded; swallow
            // An abort raised for the load we are still on means the caller
            // asked to stop, not that anything failed.
            if (err && err.name === 'AbortError') {
                viewerProgress.value = null;
                return;
            }
            viewerProgress.value = null;
            console.error(`YASTL viewer: failed to load ${fmt} model:`, err);
            viewerError.value = `Failed to load ${fmt} model`;
            throw err;
        }
    }

    /* ---- fetch + session cache ---- */

    // Small FIFO cache of downloaded buffers so re-opening a model within a
    // session skips the network. Kept small — meshes can be large.
    const _bufferCache = new Map();
    const _BUFFER_CACHE_MAX = 6;

    async function fetchBuffer(url, onProgress, signal) {
        const cached = _bufferCache.get(url);
        if (cached) {
            onProgress(1);
            return cached;
        }
        const res = await fetch(url, { signal });
        if (!res.ok) throw new Error(`fetch failed: ${res.status}`);

        const total = Number(res.headers.get('content-length')) || 0;
        let buffer;
        if (res.body && total > 0) {
            const reader = res.body.getReader();
            const chunks = [];
            let received = 0;
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                chunks.push(value);
                received += value.length;
                onProgress(Math.min(1, received / total));
            }
            const u8 = new Uint8Array(received);
            let offset = 0;
            for (const c of chunks) {
                u8.set(c, offset);
                offset += c.length;
            }
            buffer = u8.buffer;
        } else {
            buffer = await res.arrayBuffer();
            onProgress(1);
        }

        _bufferCache.set(url, buffer);
        while (_bufferCache.size > _BUFFER_CACHE_MAX) {
            _bufferCache.delete(_bufferCache.keys().next().value);
        }
        return buffer;
    }

    /* ---- parse ---- */

    function parseBuffer(buffer, fmt, opts) {
        switch (fmt) {
            case 'stl':
            case 'ply':
                return parseInWorker(buffer, fmt, opts);
            case 'glb':
            case 'gltf':
                return parseGltf(buffer);
            case 'obj':
                return Promise.resolve(parseObj(buffer));
            case '3mf':
                return Promise.resolve(parse3mf(buffer));
            case 'fbx':
                return parseFbx(buffer);
            case 'dae':
                return parseDae(buffer);
            default:
                console.warn(`YASTL viewer: unknown format "${fmt}", trying STL.`);
                return parseInWorker(buffer, 'stl', opts);
        }
    }

    let _worker = null;
    let _workerSeq = 0;
    const _workerPending = new Map();

    function getWorker() {
        if (!_worker) {
            _worker = new Worker(new URL('../viewer.worker.js', import.meta.url), {
                type: 'module',
            });
            _worker.onmessage = (e) => {
                const cb = _workerPending.get(e.data.id);
                if (cb) {
                    _workerPending.delete(e.data.id);
                    cb(e.data);
                }
            };
        }
        return _worker;
    }

    function parseInWorker(buffer, fmt, opts) {
        return new Promise((resolve, reject) => {
            let worker;
            try {
                worker = getWorker();
            } catch (e) {
                // Worker unavailable — fall back to main-thread parse.
                resolve(parseGeometryMainThread(buffer, fmt, opts));
                return;
            }
            const id = ++_workerSeq;
            _workerPending.set(id, (data) => {
                if (!data.ok) {
                    reject(new Error(data.error || 'worker parse failed'));
                    return;
                }
                const geom = new THREE.BufferGeometry();
                geom.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
                if (data.normals) {
                    geom.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
                }
                if (data.colors) {
                    geom.setAttribute('color', new THREE.BufferAttribute(
                        data.colors, data.colorItemSize || 3));
                }
                if (data.index) {
                    geom.setIndex(new THREE.BufferAttribute(data.index, 1));
                }
                resolve(data.isPoints ? pointsFromGeometry(geom) : meshFromGeometry(geom));
            });
            // Copy (no transfer) so the cached buffer stays usable for re-open.
            worker.postMessage({ id, format: fmt, buffer, smooth: !opts.flat });
        });
    }

    function meshFromGeometry(geom) {
        const material = DEFAULT_MATERIAL.clone();
        // No normals → flat shading (shader derives them) so it still renders.
        if (!geom.getAttribute('normal')) material.flatShading = true;
        const mesh = new THREE.Mesh(geom, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        return mesh;
    }

    /**
     * Wrap a face-less geometry (a PLY point cloud) in a renderable Points
     * object. sizeAttenuation is off so the cloud stays legible at any zoom
     * rather than dissolving as the camera pulls back.
     * @param {THREE.BufferGeometry} geom
     * @returns {THREE.Points}
     */
    function pointsFromGeometry(geom) {
        const hasColor = !!geom.getAttribute('color');
        const material = new THREE.PointsMaterial({
            color: hasColor ? 0xffffff : 0x2ec4b6,
            vertexColors: hasColor,
            size: 2,
            sizeAttenuation: false,
        });
        return new THREE.Points(geom, material);
    }

    // Synchronous fallback when the worker can't be created.
    function parseGeometryMainThread(buffer, fmt, opts) {
        const isPoints = fmt === 'ply' && !plyHasFaces(buffer);
        const geom = fmt === 'ply'
            ? new PLYLoader().parse(buffer)
            : new STLLoader().parse(buffer);
        if (isPoints) return pointsFromGeometry(geom);
        if (!opts.flat && !geom.getAttribute('normal')) geom.computeVertexNormals();
        return meshFromGeometry(geom);
    }

    function parseGltf(buffer) {
        return new Promise((resolve, reject) => {
            new GLTFLoader().parse(
                buffer,
                '',
                (gltf) => {
                    gltf.scene.traverse((child) => {
                        if (child.isMesh) {
                            // Decimated/converted previews come through as GLB
                            // with trimesh's UNIFORM vertex colors — not a real
                            // material, and it renders flat/pale. Give those the
                            // teal default so previews match native models; keep
                            // genuine textures or varied vertex colors.
                            const m = child.material;
                            const colorAttr = child.geometry
                                && child.geometry.getAttribute('color');
                            const hasRealColor = (m && m.map)
                                || (colorAttr && !isVertexColorUniform(colorAttr));
                            if (!hasRealColor) {
                                child.material = DEFAULT_MATERIAL.clone();
                            }
                            // Server-converted GLBs carry no NORMAL attribute,
                            // because averaging normals across a hard-surface
                            // model's shared vertices rounds off every edge and
                            // renders it soft and inflated. glTF says to flat-
                            // shade in that case, and GLTFLoader does — but the
                            // material swap above throws that flag away, and a
                            // smooth material with no normals renders unlit.
                            // Restore it from the geometry, which is the real
                            // authority either way.
                            child.material.flatShading =
                                !child.geometry.getAttribute('normal');
                            child.material.needsUpdate = true;
                            child.castShadow = true;
                            child.receiveShadow = true;
                        }
                    });
                    resolve(gltf.scene);
                },
                reject
            );
        });
    }

    function parseObj(buffer) {
        const group = new OBJLoader().parse(new TextDecoder().decode(buffer));
        group.traverse((child) => {
            if (child.isMesh) {
                child.material = DEFAULT_MATERIAL.clone();
                child.castShadow = true;
                child.receiveShadow = true;
            }
        });
        return group;
    }

    function parse3mf(buffer) {
        const group = new ThreeMFLoader().parse(buffer);
        group.traverse((child) => {
            if (child.isMesh) {
                if (!child.material || (!child.material.vertexColors && !child.material.map)) {
                    child.material = DEFAULT_MATERIAL.clone();
                } else if (child.material.vertexColors && child.geometry) {
                    // 3MF embeds slicer filament colors as vertex colors; dark
                    // filament is nearly invisible on the dark background.
                    const colorAttr = child.geometry.getAttribute('color');
                    if (colorAttr && isVertexColorDark(colorAttr)) {
                        child.material = DEFAULT_MATERIAL.clone();
                    }
                }
                child.material.side = THREE.DoubleSide;
                child.castShadow = true;
                child.receiveShadow = true;
            }
        });
        return group;
    }

    /**
     * Build a LoadingManager that refuses to fetch anything outside the model
     * file itself.
     *
     * YASTL serves a model as a single URL with no siblings, so a texture that
     * an FBX or Collada file references by relative path can never resolve —
     * requesting it only produces a 404 and a material bound to an image-less
     * sampler, which renders as a black silhouette. Blocking those requests up
     * front is both quieter and more honest, and the returned flag lets the
     * caller fall back to the default material for that model.
     *
     * Embedded media is unaffected: FBXLoader turns it into blob: URLs, which
     * resolve from memory and are allowed through.
     *
     * @returns {{ manager: THREE.LoadingManager, state: { blockedExternal: boolean } }}
     */
    function makeSelfContainedManager() {
        const state = { blockedExternal: false };
        const manager = new THREE.LoadingManager();
        // A 1x1 transparent PNG — a URL the browser can always satisfy without
        // touching the network, so the loader completes instead of erroring.
        const INERT = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
        manager.setURLModifier((url) => {
            if (typeof url === 'string' && (url.startsWith('blob:') || url.startsWith('data:'))) {
                return url;
            }
            state.blockedExternal = true;
            return INERT;
        });
        return { manager, state };
    }

    /**
     * Enable shadows, and substitute the teal default material when the model's
     * own materials cannot be honoured.
     *
     * The substitution is all-or-nothing per file. Once an external texture has
     * been blocked there is no way to tell, per material, which ones depended on
     * it — three.js assigns a Texture object synchronously and only fills in its
     * image later, so the presence of `map` says nothing about whether the image
     * will ever arrive. Falling back for the whole model is coarse but never
     * leaves half of it rendering black.
     *
     * @param {THREE.Object3D} group
     * @param {boolean} forceDefault Replace every material regardless of textures.
     */
    function applyDefaultMaterials(group, forceDefault) {
        group.traverse((child) => {
            if (!child.isMesh) return;
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            if (forceDefault || !mats.some((m) => m && m.map)) {
                child.material = DEFAULT_MATERIAL.clone();
            }
            child.castShadow = true;
            child.receiveShadow = true;
        });
    }

    /**
     * Wrap a loaded scene so it reaches addModelToScene at identity.
     *
     * addModelToScene assumes the object it is given is untransformed: it
     * measures a world-space bounding box and then overwrites scale and
     * position outright. STL, PLY, OBJ, GLB and 3MF all satisfy that, but
     * ColladaLoader applies the file's `<unit>` to the scene root and FBXLoader
     * collapses its root onto a child group that may carry a transform. Wrapping
     * preserves those transforms on the child instead of letting them be
     * clobbered, which would misplace and misscale the model.
     *
     * @param {THREE.Object3D} object
     * @returns {THREE.Group}
     */
    function wrapAtIdentity(object) {
        const wrapper = new THREE.Group();
        wrapper.add(object);
        return wrapper;
    }

    /**
     * Parse an FBX buffer.
     *
     * trimesh has no FBX loader at all, so the server cannot convert these to
     * GLB — three.js's FBXLoader is the only path that renders them. It is
     * imported lazily because it is a large module that most libraries, which
     * are overwhelmingly STL and 3MF, will never load.
     *
     * @param {ArrayBuffer} buffer
     * @returns {Promise<THREE.Object3D>}
     */
    async function parseFbx(buffer) {
        const { FBXLoader } = await import('three/examples/jsm/loaders/FBXLoader.js');
        const { manager, state } = makeSelfContainedManager();
        const group = new FBXLoader(manager).parse(buffer, '');
        applyDefaultMaterials(group, state.blockedExternal);
        return wrapAtIdentity(group);
    }

    /**
     * Parse a Collada (.dae) buffer. Same reasoning as FBX: trimesh's Collada
     * loader needs pycollada, which is not installed, so server-side GLB
     * conversion fails and this is the only working path.
     *
     * @param {ArrayBuffer} buffer
     * @returns {Promise<THREE.Object3D>}
     */
    async function parseDae(buffer) {
        const { ColladaLoader } = await import('three/examples/jsm/loaders/ColladaLoader.js');
        const { manager, state } = makeSelfContainedManager();
        const collada = new ColladaLoader(manager).parse(new TextDecoder().decode(buffer), '');
        // ColladaLoader normalises the scene to metres via the file's `<unit>`.
        // Every dimension YASTL reports — model size, bed fit, the measure tool —
        // is in millimetres, so convert rather than mislabel metres as mm.
        collada.scene.scale.multiplyScalar(1000);
        applyDefaultMaterials(collada.scene, state.blockedExternal);
        return wrapAtIdentity(collada.scene);
    }

    function disposeObject3D(object) {
        if (!object) return;
        object.traverse((child) => {
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (Array.isArray(child.material)) child.material.forEach(disposeMaterial);
                else disposeMaterial(child.material);
            }
        });
    }

    /**
     * Reset the camera to the default viewing position.
     * If a model is loaded, positions the camera to frame the model nicely.
     */
    function resetCamera() {
        if (!camera || !controls) return;

        if (currentModel) {
            const box = new THREE.Box3().setFromObject(currentModel);
            const size = box.getSize(new THREE.Vector3());
            const center = box.getCenter(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const dist = maxDim * 1.8;

            camera.position.set(
                center.x + dist * 0.7,
                center.y + dist * 0.5,
                center.z + dist * 0.7
            );
            controls.target.copy(center);
        } else {
            camera.position.set(4, 3, 4);
            controls.target.set(0, 0, 0);
        }

        camera.lookAt(controls.target);
        controls.update();
        requestRender();
    }

    /**
     * Point the camera at the model from a named direction (front/top/iso/…),
     * keeping it framed. 'fit' just re-frames from the current angle.
     */
    function setView(preset) {
        if (!camera || !controls) return;
        if (preset === 'fit') { resetCamera(); return; }
        const center = new THREE.Vector3();
        let maxDim = 4;
        if (currentModel) {
            const box = new THREE.Box3().setFromObject(currentModel);
            box.getCenter(center);
            const size = box.getSize(new THREE.Vector3());
            maxDim = Math.max(size.x, size.y, size.z) || 4;
        }
        const dist = maxDim * 1.8;
        const dirs = {
            front: [0, 0, 1], back: [0, 0, -1],
            left: [-1, 0, 0], right: [1, 0, 0],
            top: [0, 1, 0.0001], bottom: [0, -1, 0.0001],
            iso: [0.7, 0.5, 0.7],
        };
        const d = dirs[preset] || dirs.iso;
        camera.position.set(center.x + d[0] * dist, center.y + d[1] * dist, center.z + d[2] * dist);
        controls.target.copy(center);
        camera.lookAt(center);
        controls.update();
        requestRender();
    }

    /* ---- Orthographic / perspective toggle ---- */
    let isOrtho = false;

    function makeControls(cam) {
        const c = new OrbitControls(cam, renderer.domElement);
        c.enableDamping = true;
        c.dampingFactor = 0.08;
        c.screenSpacePanning = true;
        c.minDistance = 0.1;
        c.maxDistance = 500;
        c.addEventListener('change', requestRender);
        return c;
    }

    function toggleOrtho() {
        if (!camera || !renderer || !container) return;
        const w = container.clientWidth || 800;
        const h = container.clientHeight || 500;
        const pos = camera.position.clone();
        const target = controls.target.clone();
        const dist = pos.distanceTo(target);

        let next;
        if (!isOrtho) {
            const halfH = Math.tan(THREE.MathUtils.degToRad(45) / 2) * dist;
            const halfW = halfH * (w / h);
            next = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, 0.01, 10000);
        } else {
            next = new THREE.PerspectiveCamera(45, w / h, 0.01, 10000);
        }
        next.position.copy(pos);
        next.lookAt(target);

        const old = controls;
        controls = makeControls(next);
        controls.target.copy(target);
        controls.update();
        old.dispose();

        camera = next;
        isOrtho = !isOrtho;
        requestRender();
        return isOrtho;
    }

    /* ---- Point-to-point measurement ---- */
    const _raycaster = new THREE.Raycaster();
    const _pointer = new THREE.Vector2();
    let measureEnabled = false;
    let measurePoints = [];
    let measureGroup = null;
    let _downXY = null;

    function setMeasuring(on) {
        measureEnabled = on;
        if (!on) clearMeasure();
        return measureEnabled;
    }

    function clearMeasure() {
        measurePoints = [];
        measuredDistanceMm.value = null;
        if (measureGroup && scene) {
            scene.remove(measureGroup);
            disposeObject3D(measureGroup);
        }
        measureGroup = null;
        requestRender();
    }

    function onMeasureDown(e) {
        if (measureEnabled) _downXY = [e.clientX, e.clientY];
    }

    function onMeasureUp(e) {
        if (!measureEnabled || !_downXY) return;
        const moved = Math.hypot(e.clientX - _downXY[0], e.clientY - _downXY[1]);
        _downXY = null;
        if (moved > 5) return; // an orbit/pan drag, not a pick
        if (!currentModel || !renderer || !camera) return;
        const rect = renderer.domElement.getBoundingClientRect();
        _pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        _pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        _raycaster.setFromCamera(_pointer, camera);
        // Points are picked within a radius, and the default of 1 scene unit is
        // a quarter of a normalized model — far too coarse to measure with.
        _raycaster.params.Points.threshold = 0.02;
        const hits = _raycaster.intersectObject(currentModel, true);
        if (!hits.length) return;
        addMeasurePoint(hits[0].point.clone());
    }

    function addMeasurePoint(p) {
        if (measurePoints.length >= 2) measurePoints = [];
        measurePoints.push(p);
        drawMeasure();
        if (measurePoints.length === 2) {
            const dScene = measurePoints[0].distanceTo(measurePoints[1]);
            measuredDistanceMm.value = modelScaleFactor > 0
                ? dScene / modelScaleFactor
                : dScene;
        } else {
            measuredDistanceMm.value = null;
        }
        requestRender();
    }

    function drawMeasure() {
        if (measureGroup && scene) {
            scene.remove(measureGroup);
            disposeObject3D(measureGroup);
        }
        measureGroup = new THREE.Group();
        const dotGeo = new THREE.SphereGeometry(0.035, 12, 12);
        for (const p of measurePoints) {
            const dot = new THREE.Mesh(
                dotGeo.clone(),
                new THREE.MeshBasicMaterial({ color: 0x61afef, depthTest: false })
            );
            dot.position.copy(p);
            dot.renderOrder = 999;
            measureGroup.add(dot);
        }
        if (measurePoints.length === 2) {
            const g = new THREE.BufferGeometry().setFromPoints(measurePoints);
            const line = new THREE.Line(
                g,
                new THREE.LineBasicMaterial({ color: 0x61afef, depthTest: false })
            );
            line.renderOrder = 999;
            measureGroup.add(line);
        }
        if (scene) scene.add(measureGroup);
    }

    /* ---- Cross-section clipping plane ---- */
    let clipPlane = null;
    let clipEnabled = false;

    function applyClipToModel() {
        if (!currentModel) return;
        // Any object with a material, not just meshes: THREE.Points (a PLY point
        // cloud) honours clipping planes too, and skipping it would leave the
        // Clip button looking active while nothing was cut.
        currentModel.traverse((c) => {
            if (!c.material) return;
            const mats = Array.isArray(c.material) ? c.material : [c.material];
            mats.forEach((m) => {
                m.clippingPlanes = clipEnabled && clipPlane ? [clipPlane] : [];
                if (clipEnabled) {
                    // Stash the authored side so turning clipping back off does
                    // not permanently leave a front-culled material double-sided.
                    if (m.userData._yastlSide === undefined) m.userData._yastlSide = m.side;
                    m.side = THREE.DoubleSide; // reveal the cut interior
                } else if (m.userData._yastlSide !== undefined) {
                    m.side = m.userData._yastlSide;
                    delete m.userData._yastlSide;
                }
                m.needsUpdate = true;
            });
        });
    }

    function setClipping(enabled) {
        clipEnabled = enabled;
        if (renderer) renderer.localClippingEnabled = enabled;
        if (enabled && !clipPlane) {
            // Horizontal plane; normal points down so we clip away everything above.
            clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
        }
        if (enabled) setClipPosition(0.55);
        applyClipToModel();
        requestRender();
    }

    function setClipPosition(t) {
        if (!clipPlane || !currentModel) return;
        const box = new THREE.Box3().setFromObject(currentModel);
        // t=1 keeps the whole model; lower values slice down from the top.
        clipPlane.constant = box.min.y + (box.max.y - box.min.y) * t;
        requestRender();
    }

    /* ==================================================================
       Render modes

       Swaps every mesh material for a diagnostic one and keeps the original
       aside, so the model can be restored without being reloaded.

       Adapted from NexoIP 3D Viewer (MIT, (c) 2026 Iker Perez / NexoIP);
       see THIRD_PARTY_NOTICES.md.
       ================================================================== */

    /** Active mode: 'shaded' (untouched materials) | 'wireframe' | 'normals' | 'xray'. */
    let renderMode = 'shaded';
    /** mesh.uuid -> { material, castShadow } captured before a mode swap. */
    const originalMaterials = new Map();
    /** Materials this module created, tracked so they can be disposed. */
    const previewMaterials = new Set();

    /**
     * Build the diagnostic material for a mode.
     * @param {string} mode
     * @returns {THREE.Material|null} null for 'shaded' or an unknown mode.
     */
    function makePreviewMaterial(mode) {
        switch (mode) {
            case 'wireframe':
                return new THREE.MeshBasicMaterial({ color: 0x2ec4b6, wireframe: true });
            case 'normals':
                // Colors each face by its normal direction, which makes flipped
                // or inconsistently-wound faces on a print model obvious.
                return new THREE.MeshNormalMaterial({ side: THREE.DoubleSide });
            case 'xray':
                // depthWrite off so overlapping shells accumulate instead of
                // occluding each other — that stacking is what reveals interior
                // walls and infill without having to cut the model.
                return new THREE.MeshStandardMaterial({
                    color: 0x61afef,
                    transparent: true,
                    opacity: 0.28,
                    depthWrite: false,
                    side: THREE.DoubleSide,
                    roughness: 0.4,
                    metalness: 0.0,
                });
            default:
                return null;
        }
    }

    /** Put every displaced material back on its mesh and drop the previews. */
    function restoreOriginalMaterials() {
        if (currentModel && originalMaterials.size) {
            currentModel.traverse((child) => {
                if (!child.isMesh) return;
                const original = originalMaterials.get(child.uuid);
                if (!original) return;
                child.material = original.material;
                child.castShadow = original.castShadow;
            });
        }
        originalMaterials.clear();
        previewMaterials.forEach((m) => m.dispose());
        previewMaterials.clear();
    }

    /** Apply the active render mode to the current model. */
    function applyRenderMode() {
        restoreOriginalMaterials();
        if (!currentModel || renderMode === 'shaded') return;

        // One shared instance per mode: these materials carry no per-mesh
        // state, so an instance per mesh would only cost memory.
        const preview = makePreviewMaterial(renderMode);
        if (!preview) return;
        previewMaterials.add(preview);

        currentModel.traverse((child) => {
            if (!child.isMesh) return;
            originalMaterials.set(child.uuid, {
                material: child.material,
                castShadow: child.castShadow,
            });
            child.material = preview;
            // The shadow pass derives a depth material and ignores opacity, so a
            // translucent x-ray body would otherwise drop a fully solid shadow.
            if (renderMode === 'xray') child.castShadow = false;
        });
    }

    /**
     * Switch the viewer render mode.
     * @param {'shaded'|'wireframe'|'normals'|'xray'} mode
     */
    function setRenderMode(mode) {
        renderMode = mode || 'shaded';
        applyRenderMode();
        // The swap replaced the materials the clip planes were attached to.
        applyClipToModel();
        requestRender();
    }

    /**
     * Clean up all Three.js resources: stop animation, dispose geometries,
     * materials, textures, renderer, and remove the canvas from the DOM.
     */
    function dispose() {
        loadGeneration++;
        renderRequested = false;
        isOrtho = false;
        measureEnabled = false;
        measurePoints = [];
        measureGroup = null;
        measuredDistanceMm.value = null;
        viewerProgress.value = null;
        renderMode = 'shaded';
        // Terminate the parse worker and drop any pending callbacks.
        if (_worker) {
            _worker.terminate();
            _worker = null;
            _workerPending.clear();
        }
        _bufferCache.clear();
        // Stop animation
        if (animationId !== null) {
            cancelAnimationFrame(animationId);
            animationId = null;
        }

        // Stop resize observer
        if (resizeObserver) {
            resizeObserver.disconnect();
            resizeObserver = null;
        }

        // Dispose current model
        clearCurrentModel();

        // Dispose scene contents
        if (scene) {
            scene.traverse((object) => {
                if (object.geometry) object.geometry.dispose();
                if (object.material) {
                    if (Array.isArray(object.material)) {
                        object.material.forEach(disposeMaterial);
                    } else {
                        disposeMaterial(object.material);
                    }
                }
            });
            scene.clear();
            scene = null;
        }

        // Dispose gizmo scene (axis lines + sprite label textures)
        if (gizmoScene) {
            gizmoScene.traverse((object) => {
                if (object.geometry) object.geometry.dispose();
                if (object.material) {
                    if (object.material.map) object.material.map.dispose();
                    object.material.dispose();
                }
            });
            gizmoScene.clear();
            gizmoScene = null;
            gizmoCamera = null;
        }

        // Dispose controls
        if (controls) {
            controls.dispose();
            controls = null;
        }

        // Dispose renderer
        if (renderer) {
            renderer.dispose();
            if (renderer.domElement && renderer.domElement.parentNode) {
                renderer.domElement.parentNode.removeChild(renderer.domElement);
            }
            renderer = null;
        }

        camera = null;
        container = null;

        // Reset reactive state
        viewerLoading.value = false;
        viewerError.value = null;
    }

    /* ==================================================================
       Print Bed Overlay
       ================================================================== */

    /**
     * Remove the bed overlay from the scene.
     */
    function clearBedOverlay() {
        if (bedGroup && scene) {
            scene.remove(bedGroup);
            bedGroup.traverse((child) => {
                if (child.geometry) child.geometry.dispose();
                if (child.material) disposeMaterial(child.material);
            });
            bedGroup = null;
        }
        requestRender();
    }

    /**
     * Show a print bed overlay in the viewer.
     *
     * @param {{ width: number, depth: number, height: number, shape: string }} config
     *   Dimensions in mm; shape is "rectangular" or "circular".
     * @returns {{ fits: boolean }} Whether the model fits inside the bed volume.
     */
    function setBedOverlay({ width, depth, height, shape }) {
        clearBedOverlay();
        if (!scene || modelScaleFactor === 0 || !currentModel) return { fits: true };

        bedGroup = new THREE.Group();
        bedGroup.name = '__yastl_bed';

        const sw = width * modelScaleFactor;
        const sd = depth * modelScaleFactor;
        const sh = height * modelScaleFactor;

        // Center bed on model's XZ center
        const modelBox = new THREE.Box3().setFromObject(currentModel);
        const modelCenter = modelBox.getCenter(new THREE.Vector3());
        bedGroup.position.set(modelCenter.x, 0, modelCenter.z);

        // Check if model fits
        const dims = modelDimensions.value;
        let fits = true;
        if (dims) {
            if (shape === 'circular') {
                // For circular beds, width = diameter
                const radius = width / 2;
                const modelRadius = Math.sqrt(
                    Math.pow(Math.max(dims.x, 0) / 2, 2) +
                    Math.pow(Math.max(dims.z, 0) / 2, 2)
                );
                fits = modelRadius <= radius && dims.y <= height;
            } else {
                fits = dims.x <= width && dims.z <= depth && dims.y <= height;
            }
        }

        const baseColor = fits ? 0x44aacc : 0xff6633;
        const edgeMat = new THREE.LineBasicMaterial({ color: baseColor, opacity: 0.6, transparent: true });

        if (shape === 'circular') {
            const radius = sw / 2;

            // Base circle
            const circleGeo = new THREE.CircleGeometry(radius, 64);
            const circleMat = new THREE.MeshBasicMaterial({
                color: baseColor, opacity: 0.08, transparent: true, side: THREE.DoubleSide,
            });
            const circle = new THREE.Mesh(circleGeo, circleMat);
            circle.rotation.x = -Math.PI / 2;
            circle.position.y = 0.001;
            bedGroup.add(circle);

            // Base circle edge
            const ringGeo = new THREE.RingGeometry(radius - 0.01, radius, 64);
            const ringMat = new THREE.MeshBasicMaterial({
                color: baseColor, opacity: 0.5, transparent: true, side: THREE.DoubleSide,
            });
            const ring = new THREE.Mesh(ringGeo, ringMat);
            ring.rotation.x = -Math.PI / 2;
            ring.position.y = 0.002;
            bedGroup.add(ring);

            // Volume cylinder wireframe (top ring + vertical lines)
            const topRingPoints = [];
            for (let i = 0; i <= 64; i++) {
                const angle = (i / 64) * Math.PI * 2;
                topRingPoints.push(new THREE.Vector3(Math.cos(angle) * radius, sh, Math.sin(angle) * radius));
            }
            const topRingGeo = new THREE.BufferGeometry().setFromPoints(topRingPoints);
            bedGroup.add(new THREE.Line(topRingGeo, edgeMat));

            // Vertical lines (4 cardinal directions)
            for (let i = 0; i < 4; i++) {
                const angle = (i / 4) * Math.PI * 2;
                const x = Math.cos(angle) * radius;
                const z = Math.sin(angle) * radius;
                const lineGeo = new THREE.BufferGeometry().setFromPoints([
                    new THREE.Vector3(x, 0, z),
                    new THREE.Vector3(x, sh, z),
                ]);
                bedGroup.add(new THREE.Line(lineGeo, edgeMat));
            }
        } else {
            // Rectangular bed
            const halfW = sw / 2;
            const halfD = sd / 2;

            // Base plane
            const planeGeo = new THREE.PlaneGeometry(sw, sd);
            const planeMat = new THREE.MeshBasicMaterial({
                color: baseColor, opacity: 0.08, transparent: true, side: THREE.DoubleSide,
            });
            const plane = new THREE.Mesh(planeGeo, planeMat);
            plane.rotation.x = -Math.PI / 2;
            plane.position.y = 0.001;
            bedGroup.add(plane);

            // Wireframe box edges
            const corners = [
                [-halfW, 0, -halfD], [halfW, 0, -halfD],
                [halfW, 0, halfD], [-halfW, 0, halfD],
            ];
            const topCorners = corners.map(([x, , z]) => [x, sh, z]);

            // Bottom edges
            for (let i = 0; i < 4; i++) {
                const a = corners[i];
                const b = corners[(i + 1) % 4];
                const geo = new THREE.BufferGeometry().setFromPoints([
                    new THREE.Vector3(...a), new THREE.Vector3(...b),
                ]);
                bedGroup.add(new THREE.Line(geo, edgeMat));
            }

            // Top edges
            for (let i = 0; i < 4; i++) {
                const a = topCorners[i];
                const b = topCorners[(i + 1) % 4];
                const geo = new THREE.BufferGeometry().setFromPoints([
                    new THREE.Vector3(...a), new THREE.Vector3(...b),
                ]);
                bedGroup.add(new THREE.Line(geo, edgeMat));
            }

            // Vertical edges
            for (let i = 0; i < 4; i++) {
                const geo = new THREE.BufferGeometry().setFromPoints([
                    new THREE.Vector3(...corners[i]),
                    new THREE.Vector3(...topCorners[i]),
                ]);
                bedGroup.add(new THREE.Line(geo, edgeMat));
            }
        }

        scene.add(bedGroup);
        requestRender();
        return { fits };
    }

    // Auto-cleanup when the component using this composable unmounts
    onUnmounted(() => {
        dispose();
    });

    return {
        viewerLoading,
        viewerProgress,
        modelDimensions,
        initViewer,
        loadModel,
        resetCamera,
        setView,
        toggleOrtho,
        setMeasuring,
        measuredDistanceMm,
        setClipping,
        setClipPosition,
        setRenderMode,
        setViewerTheme,
        setBedOverlay,
        clearBedOverlay,
        dispose,
    };
}
