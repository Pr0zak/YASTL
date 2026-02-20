/**
 * YASTL - Three.js 3D Model Viewer
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PLYLoader } from 'three/addons/loaders/PLYLoader.js';

let scene, camera, renderer, controls, currentModel, animationId;
let container = null;

const MATERIAL = new THREE.MeshPhongMaterial({
    color: 0x0f9b8e,
    specular: 0x222222,
    shininess: 40,
    flatShading: false,
});

const MATERIAL_BACK = new THREE.MeshPhongMaterial({
    color: 0x0a7068,
    specular: 0x111111,
    shininess: 20,
    side: THREE.BackSide,
});

/**
 * Initialize the Three.js scene inside a container element.
 * @param {string} containerId - DOM element ID
 */
export function initViewer(containerId) {
    container = document.getElementById(containerId);
    if (!container) return;

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x12182a);

    // Camera
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 500;
    camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 10000);
    camera.position.set(3, 3, 3);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(w, h);
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.screenSpacePanning = true;

    // Lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight1.position.set(5, 10, 7);
    dirLight1.castShadow = true;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x8888ff, 0.3);
    dirLight2.position.set(-5, 5, -5);
    scene.add(dirLight2);

    // Grid
    const grid = new THREE.GridHelper(20, 40, 0x2a3a5c, 0x1a2a40);
    scene.add(grid);

    // Handle resize
    const ro = new ResizeObserver(() => {
        if (!container) return;
        const cw = container.clientWidth;
        const ch = container.clientHeight;
        camera.aspect = cw / ch;
        camera.updateProjectionMatrix();
        renderer.setSize(cw, ch);
    });
    ro.observe(container);

    // Animation loop
    function animate() {
        animationId = requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }
    animate();
}

/**
 * Load a 3D model from a URL into the scene.
 * @param {string} url - URL to fetch the model file
 * @param {string} format - File format (stl, obj, gltf, glb, ply, fbx, 3mf)
 */
export function loadModel(url, format) {
    // Remove previous model
    if (currentModel) {
        scene.remove(currentModel);
        currentModel.traverse((child) => {
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (Array.isArray(child.material)) {
                    child.material.forEach(m => m.dispose());
                } else {
                    child.material.dispose();
                }
            }
        });
        currentModel = null;
    }

    const fmt = (format || '').toLowerCase().replace('.', '');

    switch (fmt) {
        case 'stl':
            new STLLoader().load(url, (geometry) => {
                geometry.computeVertexNormals();
                const mesh = new THREE.Mesh(geometry, MATERIAL.clone());
                addModelToScene(mesh);
            });
            break;

        case 'obj':
            new OBJLoader().load(url, (group) => {
                group.traverse((child) => {
                    if (child.isMesh) {
                        child.material = MATERIAL.clone();
                    }
                });
                addModelToScene(group);
            });
            break;

        case 'gltf':
        case 'glb':
            new GLTFLoader().load(url, (gltf) => {
                addModelToScene(gltf.scene);
            });
            break;

        case 'ply':
            new PLYLoader().load(url, (geometry) => {
                geometry.computeVertexNormals();
                const mesh = new THREE.Mesh(geometry, MATERIAL.clone());
                addModelToScene(mesh);
            });
            break;

        default:
            console.warn(`YASTL viewer: unsupported format "${fmt}"`);
    }
}

/**
 * Add a loaded model to the scene, centering and scaling it.
 */
function addModelToScene(object) {
    // Compute bounding box
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());

    // Center the object
    object.position.sub(center);

    // Scale to fit nicely
    const maxDim = Math.max(size.x, size.y, size.z);
    if (maxDim > 0) {
        const scale = 3 / maxDim;
        object.scale.multiplyScalar(scale);
    }

    scene.add(object);
    currentModel = object;

    // Reset camera
    resetCamera();
}

/**
 * Reset camera to default position looking at the model.
 */
export function resetCamera() {
    if (!currentModel) {
        camera.position.set(3, 3, 3);
    } else {
        const box = new THREE.Box3().setFromObject(currentModel);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const dist = maxDim * 1.5;
        camera.position.set(dist, dist * 0.8, dist);
    }
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.update();
}

/**
 * Clean up all Three.js resources.
 */
export function disposeViewer() {
    if (animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
    }

    if (currentModel) {
        scene.remove(currentModel);
        currentModel.traverse((child) => {
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (Array.isArray(child.material)) {
                    child.material.forEach(m => m.dispose());
                } else {
                    child.material.dispose();
                }
            }
        });
        currentModel = null;
    }

    if (renderer) {
        renderer.dispose();
        if (renderer.domElement && renderer.domElement.parentNode) {
            renderer.domElement.parentNode.removeChild(renderer.domElement);
        }
        renderer = null;
    }

    controls = null;
    camera = null;
    scene = null;
    container = null;
}
