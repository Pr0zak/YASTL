"""Tests for app.services.hasher module."""

import pytest
import aiosqlite

from app.services.hasher import compute_file_hash, find_duplicates, CHUNK_SIZE
from app.database import init_db


class TestComputeFileHash:
    def test_returns_hex_string(self, tmp_path):
        """compute_file_hash should return a hexadecimal string."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        result = compute_file_hash(str(f))
        assert isinstance(result, str)
        # xxh128 produces a 32-character hex digest
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self, tmp_path):
        """Same content should produce the same hash."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"deterministic content")
        h1 = compute_file_hash(str(f))
        h2 = compute_file_hash(str(f))
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path):
        """Different content should produce different hashes."""
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert compute_file_hash(str(f1)) != compute_file_hash(str(f2))

    def test_empty_file(self, tmp_path):
        """Empty file should still produce a valid hash."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        result = compute_file_hash(str(f))
        assert isinstance(result, str)
        assert len(result) == 32

    def test_large_file_chunked(self, tmp_path):
        """File larger than CHUNK_SIZE should still be hashed correctly."""
        f = tmp_path / "large.bin"
        data = b"x" * (CHUNK_SIZE * 3 + 42)
        f.write_bytes(data)
        result = compute_file_hash(str(f))
        assert isinstance(result, str)
        assert len(result) == 32

    def test_nonexistent_file_raises(self, tmp_path):
        """Hashing a nonexistent file should raise OSError."""
        with pytest.raises(OSError):
            compute_file_hash(str(tmp_path / "no_such_file.bin"))


@pytest.mark.asyncio
class TestFindDuplicates:
    async def test_no_duplicates(self, db_path):
        """find_duplicates should return empty list when no matches."""
        await init_db(db_path)
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            results = await find_duplicates(conn, "nonexistent_hash")
        assert results == []

    async def test_finds_duplicates(self, db_path):
        """find_duplicates should return models with matching hash."""
        await init_db(db_path)
        shared_hash = "deadbeef" * 4

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(
                """INSERT INTO models (name, description, file_path, file_format, file_hash)
                   VALUES ('m1', '', '/tmp/a.stl', 'STL', ?)""",
                (shared_hash,),
            )
            await conn.execute(
                """INSERT INTO models (name, description, file_path, file_format, file_hash)
                   VALUES ('m2', '', '/tmp/b.stl', 'STL', ?)""",
                (shared_hash,),
            )
            await conn.commit()

            results = await find_duplicates(conn, shared_hash)

        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"m1", "m2"}
