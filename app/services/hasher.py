"""
File hashing service for duplicate detection.

Uses xxhash (xxh128) for fast, high-quality hashing of 3D model files.
Provides functions to compute hashes and query the database for duplicates.
"""

import logging

import aiosqlite
import xxhash

logger = logging.getLogger(__name__)

# Read files in 64KB chunks to keep memory usage low
CHUNK_SIZE = 64 * 1024  # 64 KB


def compute_file_hash(file_path: str) -> str:
    """
    Compute the xxh128 hash of a file.

    Reads the file in 64KB chunks for memory efficiency, making it suitable
    for large 3D model files.

    Args:
        file_path: Absolute path to the file to hash.

    Returns:
        Hexadecimal digest string of the xxh128 hash.

    Raises:
        OSError: If the file cannot be read.
    """
    hasher = xxhash.xxh128()

    logger.debug("Computing xxh128 hash for: %s", file_path)

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)

    digest = hasher.hexdigest()
    logger.debug("Hash for %s: %s", file_path, digest)
    return digest


async def find_duplicates(
    db_connection: aiosqlite.Connection,
    file_hash: str,
) -> list[dict]:
    """
    Find models in the database that share the same file hash.

    Queries the models table for all records matching the given hash,
    which indicates duplicate or identical file content.

    Args:
        db_connection: An active aiosqlite database connection.
        file_hash: The xxh128 hex digest to search for.

    Returns:
        A list of dictionaries, each representing a matching model record
        with all columns from the models table. Returns an empty list if
        no duplicates are found.
    """
    logger.debug("Searching for duplicates with hash: %s", file_hash)

    cursor = await db_connection.execute(
        "SELECT * FROM models WHERE file_hash = ?",
        (file_hash,),
    )
    rows = await cursor.fetchall()

    # Convert aiosqlite Row objects to plain dicts
    results: list[dict] = []
    for row in rows:
        results.append(dict(row))

    if results:
        logger.debug(
            "Found %d model(s) with hash %s: %s",
            len(results),
            file_hash,
            [r.get("file_path", "unknown") for r in results],
        )
    else:
        logger.debug("No duplicates found for hash: %s", file_hash)

    return results
