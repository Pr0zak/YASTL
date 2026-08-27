"""Tests for the sidebar's data: tag hygiene, category counts, category filtering.

The sidebar's problem was never mostly layout. Its default view showed 30 tags
of which 30 were punctuation fragments, its category counts disagreed with what
clicking a category returned on 30 of 53 root rows, and filtering matched
categories by name when 42 names are duplicated. These cover the fixes.
"""

import re

import pytest

from app.services.tagger import _split_filename


class TestTaggerPunctuation:
    """The auto-tagger produced the junk, and it ran on every scan."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("Chess Set (bishop).stl", ["chess", "set", "bishop"]),
            ("Rack (12u) v2", ["rack", "12u"]),
            ("80% scale", ["scale"]),
            ("Wall-Mount_v1.1", ["wall", "mount"]),
        ],
    )
    def test_punctuation_never_survives_into_a_tag(self, filename, expected):
        assert _split_filename(filename) == expected

    def test_plus_is_treated_as_a_separator(self):
        # Model sites encode spaces as '+', so this arrived as a single token
        # and became the tag '+beer+mug+(two+types)'.
        words = _split_filename("CyberDemon+Can+Holder+_+Beer+mug+(two+types)")
        assert "beer" in words and "mug" in words
        assert not any("+" in w for w in words)

    @pytest.mark.parametrize(
        "name", ["(king).stl", "part[a1mini]", "thing{x}", "a,b", "x;y"]
    )
    def test_no_token_keeps_a_bracket_or_comma(self, name):
        # Brackets in the MIDDLE of a token were the case edge-stripping missed:
        # "part[a1mini]" came out as the single tag "part[a1mini".
        assert all(not re.search(r"[()\[\]{},;]", w) for w in _split_filename(name))

    def test_bracketed_word_becomes_its_own_token(self):
        assert _split_filename("part[a1mini]") == ["part", "a1mini"]


class TestCategoryCountRollup:
    """A count of direct links answered a question nobody asked: clicking a
    category filters on it and every descendant."""

    @staticmethod
    def _tree():
        from app.api.routes_categories import _build_tree, _roll_up_counts

        rows = [
            {"id": 1, "name": "Toy", "parent_id": None, "direct_count": 1,
             "_model_ids": {10}},
            {"id": 2, "name": "Chess", "parent_id": 1, "direct_count": 2,
             "_model_ids": {11, 12}},
            {"id": 3, "name": "Pieces", "parent_id": 2, "direct_count": 2,
             "_model_ids": {12, 13}},
        ]
        tree = _build_tree(rows)
        _roll_up_counts(tree)
        return tree

    def test_root_counts_its_whole_subtree(self):
        root = self._tree()[0]
        # 10, 11, 12, 13 — not 1, and not 1+2+2.
        assert root["model_count"] == 4

    def test_a_model_linked_at_two_depths_is_counted_once(self):
        root = self._tree()[0]
        chess = root["children"][0]
        # Model 12 is on both Chess and Pieces; summing would say 4.
        assert chess["model_count"] == 3

    def test_leaf_is_unchanged(self):
        pieces = self._tree()[0]["children"][0]["children"][0]
        assert pieces["model_count"] == 2

    def test_direct_count_is_still_reported(self):
        root = self._tree()[0]
        assert root["direct_count"] == 1
