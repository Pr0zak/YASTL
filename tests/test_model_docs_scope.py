"""Tests for which sibling files count as a model's documentation.

The docs endpoint used to return every image and document in the model's parent
directory. In a library folder holding fifty models that attributes one model's
build photos — and every unrelated picture that happens to sit there — to
whichever model the user opened. These cover the filename correlation that
replaced it.
"""

import pytest

from app.api.routes_model_files import (
    _cap_images,
    _entry_scope,
    _is_folder_doc,
    _norm_stem,
    _stems_related,
    _MAX_DOC_IMAGES,
)


class TestNormStem:
    def test_strips_extension_case_and_punctuation(self):
        assert _norm_stem("Wall Mount v2.STL") == "wallmountv2"
        assert _norm_stem("wall_mount-v2.jpg") == "wallmountv2"

    def test_no_extension(self):
        assert _norm_stem("README") == "readme"

    def test_all_punctuation_reduces_to_empty(self):
        assert _norm_stem("---.png") == ""


class TestStemsRelated:
    def test_exact_match(self):
        assert _stems_related("wallmount", "wallmount")

    def test_photo_named_after_the_model(self):
        assert _stems_related("wallmount", "wallmountassembled")

    def test_model_named_after_the_photo(self):
        assert _stems_related("wallmountv2", "wallmount")

    def test_unrelated_names(self):
        assert not _stems_related("wallmount", "sloth")
        assert not _stems_related("wallmount", "pxl20250119150439199")

    def test_short_stems_do_not_match_by_prefix(self):
        # Without a floor a model called "a" would claim the whole folder.
        assert not _stems_related("a", "anythingatall")
        assert not _stems_related("abc", "abcdefgh")

    def test_floor_length_still_matches(self):
        assert _stems_related("abcd", "abcdefgh")

    def test_empty_stem_matches_nothing(self):
        assert not _stems_related("", "wallmount")
        assert not _stems_related("wallmount", "")


class TestIsFolderDoc:
    @pytest.mark.parametrize(
        "name", ["README.txt", "readme.md", "read_me.rst", "LICENSE", "licence.txt"]
    )
    def test_pack_level_documents(self, name):
        assert _is_folder_doc(name)

    @pytest.mark.parametrize("name", ["notes.txt", "wall_mount.jpg", "sloth.webp"])
    def test_ordinary_files(self, name):
        assert not _is_folder_doc(name)


class TestEntryScope:
    def test_sole_model_in_folder_keeps_everything(self):
        # The folder is the model's, so an unrelated-looking name is still its
        # own material — a photo the uploader named however they liked.
        assert _entry_scope("sloth.jpg", "wallmount", shared_folder=False) == "folder"
        assert _entry_scope("wallmount.jpg", "wallmount", shared_folder=False) == "model"

    def test_shared_folder_drops_unrelated_files(self):
        assert _entry_scope("sloth.jpg", "wallmount", shared_folder=True) is None
        assert _entry_scope("selfie.png", "wallmount", shared_folder=True) is None

    def test_shared_folder_keeps_files_named_after_the_model(self):
        assert _entry_scope("wall_mount-printed.jpg", "wallmount", shared_folder=True) == "model"

    def test_shared_folder_keeps_pack_documents_as_folder_scope(self):
        assert _entry_scope("README.txt", "wallmount", shared_folder=True) == "folder"
        assert _entry_scope("LICENSE", "wallmount", shared_folder=True) == "folder"


class TestCapImages:
    def test_documents_are_never_dropped(self):
        entries = [(f"d{i}.txt", f"d{i}.txt", "doc", 1, "folder") for i in range(40)]
        assert len(_cap_images(entries)) == 40

    def test_images_capped(self):
        entries = [(f"i{i}.png", f"i{i}.png", "image", 1, "model") for i in range(60)]
        assert len(_cap_images(entries)) == _MAX_DOC_IMAGES

    def test_cap_counts_only_images(self):
        entries = [("a.txt", "a.txt", "doc", 1, "folder")]
        entries += [(f"i{i}.png", f"i{i}.png", "image", 1, "model") for i in range(60)]
        kept = _cap_images(entries)
        assert sum(1 for e in kept if e[2] == "image") == _MAX_DOC_IMAGES
        assert sum(1 for e in kept if e[2] == "doc") == 1

    def test_order_preserved(self):
        entries = [(f"i{i}.png", f"i{i}.png", "image", 1, "model") for i in range(5)]
        assert [e[0] for e in _cap_images(entries)] == [f"i{i}.png" for i in range(5)]


class TestModelDocsOnDisk:
    """End-to-end over a real directory, covering both branches."""

    @staticmethod
    def _make_folder(tmp_path, model_name, extra):
        d = tmp_path / "pack"
        d.mkdir()
        (d / model_name).write_bytes(b"solid\n")
        for name in extra:
            (d / name).write_bytes(b"x")
        return {"id": 1, "file_path": str(d / model_name), "zip_path": None, "zip_entry": None}

    async def test_sole_model_keeps_every_sibling(self, tmp_path):
        from app.api.routes_model_files import _model_docs

        model = self._make_folder(
            tmp_path, "wall_mount.stl", ["sloth.jpg", "render.png", "README.txt"]
        )
        _, entries = await _model_docs(model, shared_folder=False)
        assert {e[1] for e in entries} == {"sloth.jpg", "render.png", "README.txt"}

    async def test_shared_folder_keeps_only_related_files(self, tmp_path):
        from app.api.routes_model_files import _model_docs

        model = self._make_folder(
            tmp_path,
            "wall_mount.stl",
            [
                "sloth.jpg",                  # unrelated photo in a library folder
                "PXL_20250119_150439199.jpg",  # someone's camera roll
                "wall_mount-printed.jpg",     # genuinely this model's
                "README.txt",                 # describes the pack
            ],
        )
        _, entries = await _model_docs(model, shared_folder=True)
        by_name = {e[1]: e[4] for e in entries}
        assert by_name == {"wall_mount-printed.jpg": "model", "README.txt": "folder"}

    async def test_shared_folder_caps_matching_images(self, tmp_path):
        from app.api.routes_model_files import _model_docs

        extra = [f"wall_mount_{i:03d}.jpg" for i in range(60)]
        model = self._make_folder(tmp_path, "wall_mount.stl", extra)
        _, entries = await _model_docs(model, shared_folder=True)
        assert sum(1 for e in entries if e[2] == "image") == _MAX_DOC_IMAGES

    async def test_missing_file_returns_nothing(self, tmp_path):
        from app.api.routes_model_files import _model_docs

        model = {"id": 1, "file_path": str(tmp_path / "gone.stl"),
                 "zip_path": None, "zip_entry": None}
        assert await _model_docs(model, shared_folder=True) == (None, [])
