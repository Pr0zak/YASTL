/**
 * YASTL - Three.js 3D Model Viewer
 *
 * Provides functions to initialize a Three.js scene inside a DOM container,
 * load 3D models in various formats, and clean up resources.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PLYLoader } from 'three/addons/loaders/PLYLoader.js';
import { ThreeMFLoader } from 'three/addons/loaders/3MFLoader.js';

/* ---- Module-level state ---- */
let scene = null;
let camera = null;
let renderer = null;
let controls = null;
let currentModel = null;
let animationId = null;
let container = null;
let resizeObserver = null;

/** Default material for models that don't carry their own (teal accent). */
const DEFAULT_MATERIAL = new THREE.MeshPhongMaterial({
    color: 0x0f9b8e,
    specular: 0x333333,
    shininess: 50,
    flatShading: false,
    side: THREE.DoubleSide,
});

/* ==================================================================
   Public API
   ================================================================== */

/**
 * Initialize the Three.js scene, camera, renderer, controls, lights, and grid
 * inside the given container element.
 *
 * @param {string} containerId - The id of the DOM element to render into.
 */
export function initViewer(containerId) {
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
 * @param {string} format - File format string (e.g. "stl", "obj", "gltf", "glb", "ply", "fbx").
 * @returns {Promise<void>}
 */
export function loadModel(url, format) {
    // Clear previous model
    clearCurrentModel();

    const fmt = (format || '').toLowerCase().replace(/^\./, '');

    return new Promise((resolve, reject) => {
        const onError = (err) => {
            console.error(`YASTL viewer: failed to load ${fmt} model:`, err);
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
export function resetCamera() {
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
export function disposeViewer() {
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
}

/* ==================================================================
   Internal helpers
   ================================================================== */

/**
 * Add a loaded 3D object to the scene, centering it on the origin
 * and auto-scaling it to fit a reasonable viewing size.
 *
 * @param {THREE.Object3D} object - The loaded model/group.
 */
function addModelToScene(object) {
    if (!scene) return;

    // Compute bounding box
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

    // Center the model on the origin
    object.position.sub(center);

    // Auto-scale to fit within a normalized size
    const maxDim = Math.max(size.x, size.y, size.z);
    if (maxDim > 0) {
        const targetSize = 4;
        const scale = targetSize / maxDim;
        object.scale.multiplyScalar(scale);
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
}

/**
 * Dispose a material and any textures it references.
 *
 * @param {THREE.Material} material
 */
function disposeMaterial(material) {
    if (!material) return;
    // Dispose any textures attached to the material
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
