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

/**
 * Create a new viewer instance scoped to the calling component.
 *
 * @returns {{ viewerLoading: import('vue').Ref<boolean>, viewerError: import('vue').Ref<string|null>, initViewer: Function, loadModel: Function, resetCamera: Function, dispose: Function }}
 */
export function useViewer() {
    /* ---- Reactive state exposed to the component ---- */
    const viewerLoading = ref(false);
    const viewerError = ref(null);
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

    /** Scale factor applied to the model (mm → scene units). */
    let modelScaleFactor = 0;
    /** Group holding all bed overlay meshes. */
    let bedGroup = null;

    /** Default material for models that don't carry their own (teal accent). */
    const DEFAULT_MATERIAL = new THREE.MeshPhongMaterial({
        color: 0x0f9b8e,
        specular: 0x333333,
        shininess: 50,
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
            if (material[prop]) {
                material[prop].dispose();
            }
        }
        material.dispose();
    }

    /**
     * Remove and dispose the current model from the scene.
     */
    function clearCurrentModel() {
        if (currentModel && scene) {
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
        clearBedOverlay();
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

        // Center the model on the origin
        object.position.sub(center);

        // Auto-scale to fit within a normalized size
        const maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim > 0) {
            const targetSize = 4;
            const scale = targetSize / maxDim;
            modelScaleFactor = scale;
            object.scale.multiplyScalar(scale);
        } else {
            modelScaleFactor = 1;
        }

        // Lift model so its bottom sits on the grid (y=0)
        const scaledBox = new THREE.Box3().setFromObject(object);
        const yOffset = -scaledBox.min.y;
        object.position.y += yOffset;

        scene.add(object);
        currentModel = object;

        // Position camera to see the model
        resetCamera();
    }

    /* ==================================================================
       Public API
       ================================================================== */

    /**
     * Initialize the Three.js scene, camera, renderer, controls, lights, and grid
     * inside the given container element.
     *
     * @param {string} containerId - The id of the DOM element to render into.
     */
    function initViewer(containerId) {
        container = document.getElementById(containerId);
        if (!container) {
            console.warn('YASTL viewer: container not found:', containerId);
            return;
        }

        const w = container.clientWidth || 800;
        const h = container.clientHeight || 500;

        // ---- Scene ----
        scene = new THREE.Scene();
        scene.background = new THREE.Color(0x12182a);

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
        renderer.toneMappingExposure = 1.0;
        container.appendChild(renderer.domElement);

        // ---- Controls ----
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.screenSpacePanning = true;
        controls.minDistance = 0.1;
        controls.maxDistance = 500;

        // ---- Lights ----
        // Soft ambient fill
        const ambient = new THREE.AmbientLight(0xffffff, 0.45);
        scene.add(ambient);

        // Main directional (key light)
        const keyLight = new THREE.DirectionalLight(0xffffff, 0.85);
        keyLight.position.set(5, 10, 7);
        keyLight.castShadow = true;
        keyLight.shadow.mapSize.set(1024, 1024);
        scene.add(keyLight);

        // Secondary directional (fill light, slightly blue)
        const fillLight = new THREE.DirectionalLight(0x8899bb, 0.35);
        fillLight.position.set(-5, 5, -5);
        scene.add(fillLight);

        // ---- Grid ----
        const grid = new THREE.GridHelper(20, 40, 0x2a3a5c, 0x1e2a40);
        grid.material.opacity = 0.6;
        grid.material.transparent = true;
        scene.add(grid);

        // ---- Resize handling ----
        resizeObserver = new ResizeObserver(() => {
            if (!container || !renderer || !camera) return;
            const cw = container.clientWidth;
            const ch = container.clientHeight;
            if (cw === 0 || ch === 0) return;
            camera.aspect = cw / ch;
            camera.updateProjectionMatrix();
            renderer.setSize(cw, ch);
        });
        resizeObserver.observe(container);

        // ---- Animation loop ----
        function animate() {
            animationId = requestAnimationFrame(animate);
            if (controls) controls.update();
            if (renderer && scene && camera) {
                renderer.render(scene, camera);
            }
        }
        animate();
    }

    /**
     * Load a 3D model from a URL into the current scene.
     * Clears any previously loaded model first. Uses the appropriate
     * loader based on the file format.
     *
     * @param {string} url - URL to fetch the model file.
     * @param {string} format - File format string (e.g. "stl", "obj", "gltf", "glb", "ply", "3mf").
     * @returns {Promise<void>}
     */
    function loadModel(url, format) {
        // Clear previous model
        clearCurrentModel();
        viewerError.value = null;

        const fmt = (format || '').toLowerCase().replace(/^\./, '');

        return new Promise((resolve, reject) => {
            const onError = (err) => {
                console.error(`YASTL viewer: failed to load ${fmt} model:`, err);
                viewerError.value = `Failed to load ${fmt} model`;
                reject(err);
            };

            switch (fmt) {
                case 'stl':
                    new STLLoader().load(
                        url,
                        (geometry) => {
                            geometry.computeVertexNormals();
                            const mesh = new THREE.Mesh(geometry, DEFAULT_MATERIAL.clone());
                            mesh.castShadow = true;
                            mesh.receiveShadow = true;
                            addModelToScene(mesh);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;

                case 'obj':
                    new OBJLoader().load(
                        url,
                        (group) => {
                            group.traverse((child) => {
                                if (child.isMesh) {
                                    child.material = DEFAULT_MATERIAL.clone();
                                    child.castShadow = true;
                                    child.receiveShadow = true;
                                }
                            });
                            addModelToScene(group);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;

                case 'gltf':
                case 'glb':
                    new GLTFLoader().load(
                        url,
                        (gltf) => {
                            // Use model's own materials for glTF
                            gltf.scene.traverse((child) => {
                                if (child.isMesh) {
                                    child.castShadow = true;
                                    child.receiveShadow = true;
                                }
                            });
                            addModelToScene(gltf.scene);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;

                case 'ply':
                    new PLYLoader().load(
                        url,
                        (geometry) => {
                            geometry.computeVertexNormals();
                            const mesh = new THREE.Mesh(geometry, DEFAULT_MATERIAL.clone());
                            mesh.castShadow = true;
                            mesh.receiveShadow = true;
                            addModelToScene(mesh);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;

                case '3mf':
                    new ThreeMFLoader().load(
                        url,
                        (group) => {
                            group.traverse((child) => {
                                if (child.isMesh) {
                                    if (!child.material || (!child.material.vertexColors && !child.material.map)) {
                                        child.material = DEFAULT_MATERIAL.clone();
                                    }
                                    child.material.side = THREE.DoubleSide;
                                    child.castShadow = true;
                                    child.receiveShadow = true;
                                }
                            });
                            addModelToScene(group);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;

                default:
                    console.warn(`YASTL viewer: unsupported format "${fmt}". Attempting STL loader as fallback.`);
                    new STLLoader().load(
                        url,
                        (geometry) => {
                            geometry.computeVertexNormals();
                            const mesh = new THREE.Mesh(geometry, DEFAULT_MATERIAL.clone());
                            addModelToScene(mesh);
                            resolve();
                        },
                        undefined,
                        onError
                    );
                    break;
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
    }

    /**
     * Clean up all Three.js resources: stop animation, dispose geometries,
     * materials, textures, renderer, and remove the canvas from the DOM.
     */
    function dispose() {
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
        return { fits };
    }

    // Auto-cleanup when the component using this composable unmounts
    onUnmounted(() => {
        dispose();
    });

    return {
        viewerLoading,
        modelDimensions,
        initViewer,
        loadModel,
        resetCamera,
        setBedOverlay,
        clearBedOverlay,
        dispose,
    };
}
