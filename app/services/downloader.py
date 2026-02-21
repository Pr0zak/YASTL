"""File download utilities for the model import pipeline.

Handles downloading files from URLs, including special handling for
S3 presigned URLs that must not have their query strings re-encoded.
"""

import asyncio
import logging
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, unquote

import httpx

from app.services.scrapers import _DEFAULT_HEADERS

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "download"


def _deduplicate_path(dest: Path) -> Path:
    """Append _1, _2, etc. if the file already exists."""
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _is_presigned_s3(url: str) -> bool:
    """Check if a URL is an AWS S3 presigned URL (v2 or v4)."""
    return "amazonaws.com" in url and ("Signature=" in url or "X-Amz-Signature=" in url)


def _download_raw(url: str, dest: Path) -> None:
    """Download using urllib to preserve the exact URL (no re-encoding).

    httpx and other clients parse and re-encode query parameters, which
    breaks S3 presigned URL signatures when they contain + or / characters.
    urllib.request.urlopen sends the URL byte-for-byte as provided.
    """
    req = urllib.request.Request(url, headers=dict(_DEFAULT_HEADERS))
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)


async def download_file(
    url: str,
    client: httpx.AsyncClient,
    dest_dir: Path,
    filename: str | None = None,
) -> Path:
    """Stream-download a file to dest_dir.

    Detects filename from Content-Disposition header or URL path if not provided.
    For S3 presigned URLs, uses urllib to avoid re-encoding the signature.
    Returns the path to the saved file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    use_raw = _is_presigned_s3(url)

    if use_raw:
        # Use urllib for presigned S3 URLs to preserve exact query string
        if not filename:
            path_part = urlparse(url).path
            filename = unquote(path_part.rsplit("/", 1)[-1]) or "download"
        filename = _sanitize_filename(filename)
        dest = _deduplicate_path(dest_dir / filename)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _download_raw, url, dest)
    else:
        async with client.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()

            # Determine filename
            if not filename:
                # Try Content-Disposition
                cd = resp.headers.get("content-disposition", "")
                match = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', cd)
                if match:
                    filename = unquote(match.group(1).strip())
                else:
                    # Fall back to URL path
                    path_part = urlparse(str(resp.url)).path
                    filename = unquote(path_part.rsplit("/", 1)[-1]) or "download"

            filename = _sanitize_filename(filename)
            dest = _deduplicate_path(dest_dir / filename)

            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)

    logger.info("Downloaded %s -> %s", url, dest)
    return dest
