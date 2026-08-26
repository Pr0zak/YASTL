/**
 * PLY header inspection.
 *
 * A PLY file can hold either a triangulated surface or a bare point cloud;
 * only the header's `element face` line tells them apart. Wrapping a point
 * cloud in a THREE.Mesh produces an object with no faces, which renders as
 * nothing at all — so the format has to be classified before it is parsed.
 *
 * Adapted from NexoIP 3D Viewer (MIT, (c) 2026 Iker Perez / NexoIP);
 * see THIRD_PARTY_NOTICES.md.
 */

/** How much of the file to decode when looking for the header. */
const HEADER_SCAN_BYTES = 64 * 1024;

/**
 * Report whether a PLY buffer declares at least one face.
 *
 * The header is ASCII even in binary PLY files, and ends at `end_header`, so
 * decoding the first chunk is enough. A buffer with no recognisable header is
 * reported as a mesh: that is what the viewer assumed before point clouds were
 * handled, and preserving it keeps unusual-but-working files working.
 *
 * @param {ArrayBuffer} buffer Raw PLY file contents.
 * @returns {boolean} True when the header declares one or more faces.
 */
export function plyHasFaces(buffer) {
    const scan = new Uint8Array(buffer, 0, Math.min(buffer.byteLength, HEADER_SCAN_BYTES));
    const text = new TextDecoder('ascii').decode(scan);
    // Anchor the terminator to its own line. A bare indexOf would also match the
    // token inside a `comment` or `obj_info` line, truncating the header before
    // the real element declarations and misreading a mesh as a point cloud.
    const terminator = text.match(/^end_header\s*$/im);
    if (!terminator) return true;
    const match = text.slice(0, terminator.index).match(/^element\s+face\s+(\d+)\s*$/im);
    return Number((match && match[1]) || 0) > 0;
}
