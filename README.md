# YASTL - Yet Another STL

A personal 3D model library web application for browsing, searching, and previewing 3D model files. Built with Python/FastAPI backend and Vue 3 frontend with Three.js for interactive 3D viewing.

## Features

- **Wide format support**: STL, OBJ, glTF/GLB, 3MF, STEP, FBX, PLY, DAE, OFF
- **Interactive 3D viewer**: Three.js-powered in-browser model preview with orbit controls
- **Full-text search**: SQLite FTS5 search across model names and descriptions
- **Auto-import**: Directory scanner with file watcher for automatic library updates
- **Server-side thumbnails**: Auto-generated preview images for grid view
- **Duplicate detection**: xxHash-based file deduplication
- **Tags & categories**: Organize models with flat tags and hierarchical categories (auto-created from directory structure)
- **Dark theme UI**: Modern, responsive interface with grid/list views

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+ / FastAPI |
| Database | SQLite 3 with FTS5 |
| 3D Processing | trimesh, numpy-stl, Pillow |
| File Watching | watchdog |
| Frontend | Vue 3 (CDN) + Three.js |
| Hashing | xxhash (xxh128) |

## Quick Start

### Docker Compose

```bash
# Edit docker-compose.yml to set your model directory path
docker compose up -d
```

The app will be available at `http://localhost:8000`.

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YASTL_MODEL_LIBRARY_DB` | `/data/library.db` | SQLite database path |
| `YASTL_MODEL_LIBRARY_SCAN_PATH` | `/nfs/DATA/3dPrinting` | Directory to scan for models |
| `YASTL_MODEL_LIBRARY_THUMBNAIL_PATH` | `/data/thumbnails` | Thumbnail storage directory |

## Proxmox LXC Deployment

A setup script is provided for deploying to a Proxmox LXC container with NFS mount:

```bash
export NFS_SERVER=192.168.1.100
export NFS_SHARE=/volume1/3dPrinting
chmod +x deploy/proxmox-setup.sh
./deploy/proxmox-setup.sh
```

See `deploy/proxmox-setup.sh` for all configuration options.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models` | List models (paginated, filterable) |
| GET | `/api/models/{id}` | Get model details |
| PUT | `/api/models/{id}` | Update model name/description |
| DELETE | `/api/models/{id}` | Remove model from library |
| GET | `/api/models/{id}/file` | Download/serve 3D file |
| GET | `/api/models/{id}/thumbnail` | Serve thumbnail image |
| POST | `/api/models/{id}/tags` | Add tags to model |
| GET | `/api/models/duplicates` | Find duplicate files |
| GET | `/api/search?q=query` | Full-text search |
| GET | `/api/tags` | List all tags |
| GET | `/api/categories` | List category tree |
| POST | `/api/scan` | Trigger library scan |
| GET | `/api/scan/status` | Check scan progress |
