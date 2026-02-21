"""Site-specific metadata scraping for 3D model hosting sites.

Detects which hosting site a URL belongs to (Thingiverse, MakerWorld,
Printables, MyMiniFactory, Cults3D, Thangs) and scrapes metadata
(title, description, tags, download URLs) using site-specific APIs
or generic Open Graph tag extraction.
"""

import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Browser-like headers to avoid basic bot detection
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Site detection
# ---------------------------------------------------------------------------

SITE_HOSTS: dict[str, str] = {
    "thingiverse.com": "thingiverse",
    "www.thingiverse.com": "thingiverse",
    "makerworld.com": "makerworld",
    "www.makerworld.com": "makerworld",
    "printables.com": "printables",
    "www.printables.com": "printables",
    "myminifactory.com": "myminifactory",
    "www.myminifactory.com": "myminifactory",
    "cults3d.com": "cults3d",
    "www.cults3d.com": "cults3d",
    "thangs.com": "thangs",
    "www.thangs.com": "thangs",
}

# Extensions we treat as downloadable 3D model files
MODEL_EXTENSIONS: set[str] = {
    ".stl", ".obj", ".gltf", ".glb", ".3mf",
    ".ply", ".dae", ".off", ".step", ".stp", ".fbx", ".zip",
}


def detect_site(url: str) -> str | None:
    """Identify the hosting site from a URL, or None for unknown/direct links."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    return SITE_HOSTS.get(host.lower())


# ---------------------------------------------------------------------------
# Metadata scraping helpers
# ---------------------------------------------------------------------------

async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """GET a URL and return its text content."""
    resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _extract_og_metadata(html: str) -> dict:
    """Extract Open Graph meta tags from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    description = None

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()

    if not title:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

    # Attempt to extract tags from meta keywords
    tags: list[str] = []
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        tags = [t.strip() for t in meta_kw["content"].split(",") if t.strip()]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "download_urls": [],
    }


# ---------------------------------------------------------------------------
# Per-site scrapers
# ---------------------------------------------------------------------------

async def _scrape_thingiverse(
    client: httpx.AsyncClient, url: str, credentials: dict | None = None,
) -> dict:
    """Scrape metadata from Thingiverse.

    If an API key is provided in credentials, uses the REST API for richer data.
    Otherwise falls back to og: tag scraping.
    """
    # Extract thing ID from URL
    match = re.search(r"thing[:/](\d+)", url, re.IGNORECASE)
    thing_id = match.group(1) if match else None

    api_key = (credentials or {}).get("api_key")
    if thing_id and api_key:
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            thing_resp = await client.get(
                f"https://api.thingiverse.com/things/{thing_id}",
                headers=headers,
            )
            thing_resp.raise_for_status()
            thing_data = thing_resp.json()

            files_resp = await client.get(
                f"https://api.thingiverse.com/things/{thing_id}/files",
                headers=headers,
            )
            files_resp.raise_for_status()
            files_data = files_resp.json()

            download_urls = [
                f.get("public_url") or f.get("download_url", "")
                for f in files_data
                if f.get("public_url") or f.get("download_url")
            ]

            tags = [t.get("name", "") for t in thing_data.get("tags", []) if t.get("name")]

            return {
                "title": thing_data.get("name"),
                "description": thing_data.get("description", ""),
                "tags": tags,
                "download_urls": download_urls,
                "source_site": "thingiverse",
            }
        except Exception as e:
            logger.warning("Thingiverse API failed for thing %s: %s, falling back to scrape", thing_id, e)

    # Fallback: og: tag scraping
    html = await _fetch_page(client, url)
    meta = _extract_og_metadata(html)
    meta["source_site"] = "thingiverse"

    # Try to find download links in page
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "/download" in href or any(href.lower().endswith(ext) for ext in MODEL_EXTENSIONS):
            if href.startswith("/"):
                href = f"https://www.thingiverse.com{href}"
            meta["download_urls"].append(href)

    return meta


async def _scrape_makerworld(
    client: httpx.AsyncClient, url: str, credentials: dict | None = None,
) -> dict:
    """Scrape MakerWorld metadata via the Bambu Lab API.

    MakerWorld's website is behind Cloudflare challenges, but the Bambu Lab
    API at api.bambulab.com is accessible with a Bearer token. The token
    can be found in the browser cookies as 'token' on makerworld.com.

    Uses two API endpoints:
    - GET /v1/design-service/design/{id} -- metadata, tags, instances
    - GET /v1/iot-service/api/user/profile/{profileId}?model_id={modelId}
      -- signed S3 download URLs for 3MF files
    """
    meta: dict = {
        "title": None,
        "description": None,
        "tags": [],
        "download_urls": [],
        "source_site": "makerworld",
        "error": None,
    }

    token = (credentials or {}).get("token", "")
    if not token:
        meta["error"] = (
            "MakerWorld requires your Bambu Lab token. "
            "Add it in Settings \u2192 Import Credentials \u2192 MakerWorld."
        )
        logger.warning("MakerWorld import attempted without token credential")
        return meta

    # Extract design ID from URL like /models/2397308-some-name
    match = re.search(r"/models/(\d+)", url)
    if not match:
        meta["error"] = "Could not extract model ID from MakerWorld URL"
        return meta

    design_id = match.group(1)
    auth_headers = {"Authorization": f"Bearer {token}"}
    api_base = "https://api.bambulab.com/v1"

    # Step 1: Fetch design metadata
    try:
        resp = await client.get(
            f"{api_base}/design-service/design/{design_id}",
            headers=auth_headers,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            meta["error"] = "MakerWorld token is expired. Update it in Settings \u2192 Import Credentials."
        else:
            meta["error"] = f"Bambu Lab API returned HTTP {e.response.status_code}"
        logger.warning("MakerWorld API failed for design %s: HTTP %s", design_id, e.response.status_code)
        return meta
    except Exception as e:
        meta["error"] = f"API request failed: {e}"
        logger.warning("MakerWorld API failed for design %s: %s", design_id, e)
        return meta

    meta["title"] = data.get("title")
    meta["description"] = data.get("summary") or data.get("description") or ""
    # Use translated tags if available (English), fall back to original
    meta["tags"] = data.get("tagsTranslated") or data.get("tags") or []

    # Step 2: Get download URLs from profile instances
    model_id = data.get("modelId")
    instances = data.get("instances") or []

    for instance in instances:
        profile_id = instance.get("profileId")
        if not profile_id or not model_id:
            continue
        try:
            prof_resp = await client.get(
                f"{api_base}/iot-service/api/user/profile/{profile_id}",
                params={"model_id": model_id},
                headers=auth_headers,
            )
            prof_resp.raise_for_status()
            prof_data = prof_resp.json()

            dl_url = prof_data.get("url")
            if dl_url:
                meta["download_urls"].append(dl_url)
                # Only need one profile's files
                break
        except Exception as e:
            logger.debug("Failed to get profile %s download URL: %s", profile_id, e)
            continue

    if not meta["download_urls"]:
        meta["error"] = "Metadata loaded but no downloadable files found"

    return meta


async def _scrape_printables(
    client: httpx.AsyncClient, url: str, _credentials: dict | None = None,
) -> dict:
    """Scrape Printables metadata via their GraphQL API."""
    meta: dict = {
        "title": None,
        "description": None,
        "tags": [],
        "download_urls": [],
        "source_site": "printables",
    }

    # Extract model ID from URL like /model/12345-some-name
    match = re.search(r"/model/(\d+)", url)
    if not match:
        # Fall back to generic scraping
        return await _scrape_generic(client, url, "printables", _credentials)

    model_id = match.group(1)

    try:
        query = """
        query PrintProfile($id: ID!) {
            print(id: $id) {
                name
                description
                tags { name }
                stls { id name fileSize }
                gcodes { id name fileSize }
            }
        }
        """
        resp = await client.post(
            "https://api.printables.com/graphql/",
            json={"query": query, "variables": {"id": model_id}},
        )
        resp.raise_for_status()
        data = resp.json()
        print_data = (data.get("data") or {}).get("print") or {}

        meta["title"] = print_data.get("name")
        meta["description"] = print_data.get("description", "")
        meta["tags"] = [t["name"] for t in (print_data.get("tags") or []) if t.get("name")]

        # Printables download URLs follow a pattern
        for stl in (print_data.get("stls") or []):
            stl_id = stl.get("id")
            if stl_id:
                meta["download_urls"].append(
                    f"https://media.printables.com/media/prints/{model_id}/stls/{stl_id}/{stl.get('name', 'model.stl')}"
                )
    except Exception as e:
        logger.warning("Printables GraphQL failed for model %s: %s, falling back to scrape", model_id, e)
        return await _scrape_generic(client, url, "printables", _credentials)

    return meta


async def _scrape_generic(
    client: httpx.AsyncClient, url: str, site_name: str, _credentials: dict | None = None,
) -> dict:
    """Generic og: tag scraper for sites without specific API support."""
    try:
        html = await _fetch_page(client, url)
    except httpx.HTTPStatusError as e:
        logger.warning("Failed to fetch %s (HTTP %s), metadata unavailable", url, e.response.status_code)
        return {
            "title": None,
            "description": None,
            "tags": [],
            "download_urls": [],
            "source_site": site_name,
        }
    meta = _extract_og_metadata(html)
    meta["source_site"] = site_name

    # Try to find download links
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if any(href.lower().endswith(ext) for ext in MODEL_EXTENSIONS):
            if href.startswith("/"):
                parsed = urlparse(url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            meta["download_urls"].append(href)

    return meta


# Scraper registry: maps site key to async scraper function
_SCRAPERS: dict[str, callable] = {
    "thingiverse": _scrape_thingiverse,
    "makerworld": _scrape_makerworld,
    "printables": _scrape_printables,
}

# Generic sites use the same og: scraper
for _site in ("myminifactory", "cults3d", "thangs"):
    _SCRAPERS[_site] = lambda client, url, creds=None, s=_site: _scrape_generic(client, url, s, creds)


async def scrape_metadata(
    url: str, credentials: dict | None = None,
) -> dict:
    """Detect site and scrape metadata for a URL.

    Returns dict with keys: title, description, tags, download_urls, source_site.
    """
    site = detect_site(url)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=_DEFAULT_HEADERS) as client:
        if site and site in _SCRAPERS:
            site_creds = (credentials or {}).get(site)
            return await _SCRAPERS[site](client, url, site_creds)
        else:
            # Unknown site / direct link
            return {
                "title": None,
                "description": None,
                "tags": [],
                "download_urls": [url],
                "source_site": None,
            }
