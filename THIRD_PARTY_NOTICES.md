# Third-Party Notices

YASTL bundles and adapts third-party code. This file records the notices those
components require. It covers source that was **copied or adapted into this
repository**; ordinary dependencies installed from PyPI and npm carry their own
licenses in their own packages and are not restated here.

---

## NexoIP 3D Viewer

Several viewer functions were adapted from NexoIP 3D Viewer, an MIT-licensed
Electron 3D viewer by Iker Perez.

- **Upstream:** https://github.com/ikerperez12/NexoIP-3D-Viewer
- **License:** MIT
- **Adapted in:**
  - `frontend/src/ply.js` — PLY header inspection, to tell a point cloud apart
    from a triangulated mesh. Adapted from the upstream `plyHasFaces` in
    `src/utils/loaders.js`.
  - `frontend/src/composables/useViewer.js` — the render-mode material swap
    (wireframe, surface normals, x-ray), adapted from `applyRenderMode` in
    `src/components/Viewport3D.jsx`; and the shape of the FBX and Collada
    loader entry points, adapted from `loadFbx`/`loadDae` in
    `src/utils/loaders.js`.

The adapted code was reworked to fit YASTL's Vue composable structure, palette,
and on-demand rendering loop; behaviour differs from upstream in places. Bugs
in it are YASTL's, not NexoIP's.

### License text

```
MIT License

Copyright (c) 2026 Iker Perez / NexoIP

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
