/**
 * YASTL viewer parse worker.
 *
 * Parses STL/PLY ArrayBuffers off the main thread — including the
 * expensive computeVertexNormals — and posts back transferable geometry
 * arrays so the main thread only wraps them in a BufferGeometry. This is
 * what keeps the UI responsive while a large model loads.
 */
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';

self.onmessage = (e) => {
    const { id, format, buffer, smooth } = e.data;
    try {
        let geom;
        if (format === 'stl') {
            geom = new STLLoader().parse(buffer);
        } else if (format === 'ply') {
            geom = new PLYLoader().parse(buffer);
        } else {
            throw new Error(`unsupported worker format: ${format}`);
        }

        // STL binary carries per-face normals (faceted); PLY/ASCII may not.
        // Only compute smooth normals when asked and none are present —
        // this is the costly O(triangles) step, now off the main thread.
        if (smooth && !geom.getAttribute('normal')) {
            geom.computeVertexNormals();
        }

        const position = geom.getAttribute('position');
        const normal = geom.getAttribute('normal');
        const index = geom.index;

        const msg = { id, ok: true, positions: position.array };
        const transfer = [position.array.buffer];
        if (normal) {
            msg.normals = normal.array;
            transfer.push(normal.array.buffer);
        }
        if (index) {
            msg.index = index.array;
            transfer.push(index.array.buffer);
        }
        self.postMessage(msg, transfer);
    } catch (err) {
        self.postMessage({ id, ok: false, error: String((err && err.message) || err) });
    }
};
