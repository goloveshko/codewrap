"""Tests for pure helper functions in codewrap.utils."""

import os
from pathlib import Path

import pytest

from codewrap.models import TargetRule
from codewrap.utils import BINARY_EXTENSIONS, infer_common_root, is_binary_file, parse_target_arg


def same_path(a: Path | str, b: Path | str) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


class TestParseTargetArg:
    def test_folder_with_extensions(self):
        rule = parse_target_arg("folder:py,toml")
        assert rule.path == "folder"
        assert rule.extensions == ["py", "toml"]

    def test_plain_path(self):
        rule = parse_target_arg("src/module.py")
        assert rule.path == "src/module.py"
        assert rule.extensions == []

    def test_windows_drive_letter_not_split(self):
        rule = parse_target_arg(r"C:\proj\file.py")
        assert rule.path == r"C:\proj\file.py"

    def test_colon_with_slash_in_tail_is_path(self):
        rule = parse_target_arg("name.md:sub/file")
        assert rule.path == "name.md:sub/file"

    def test_spaces_stripped(self):
        rule = parse_target_arg("  src : py , md  ")
        assert rule.path == "src"
        assert rule.extensions == ["py", "md"]


class TestInferCommonRoot:
    def test_empty_rules_returns_default(self, tmp_path: Path):
        result = infer_common_root([], tmp_path)
        assert same_path(result, tmp_path)

    def test_files_in_same_dir(self, tmp_path: Path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        rules = [TargetRule(path=str(a)), TargetRule(path=str(b))]
        assert same_path(infer_common_root(rules, tmp_path), tmp_path)

    def test_sibling_dirs_share_parent(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        rules = [TargetRule(path=str(tmp_path / "src")), TargetRule(path=str(tmp_path / "tests"))]
        assert same_path(infer_common_root(rules, tmp_path), tmp_path)

    def test_no_prefix_false_match_regression(self, tmp_path: Path):
        """Regression for review #7: '/proj/foo' must not be a common root of '/proj/foobar'."""
        proj = tmp_path / "proj"
        (proj / "foo").mkdir(parents=True)
        (proj / "foobar").mkdir()
        (proj / "foobar" / "f.py").write_text("")
        rules = [
            TargetRule(path=str(proj / "foo")),
            TargetRule(path=str(proj / "foobar" / "f.py")),
        ]
        assert same_path(infer_common_root(rules, tmp_path), proj)

    def test_relative_rules_resolved_against_default(self, tmp_path: Path):
        """Regression for review #7: relative rules must not silently drop out."""
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()
        rules = [TargetRule(path="src"), TargetRule(path="docs")]
        assert same_path(infer_common_root(rules, tmp_path), tmp_path)

    @pytest.mark.skipif(os.name != "nt", reason="multi-drive paths are Windows-specific")
    def test_mixed_drives_fall_back_to_default(self, tmp_path: Path):
        rules = [TargetRule(path=r"C:\one\a.py"), TargetRule(path=r"D:\two\b.py")]
        assert same_path(infer_common_root(rules, tmp_path), tmp_path)


class TestIsBinaryFile:
    def test_binary_by_extension(self, tmp_path: Path):
        f = tmp_path / "img.png"
        f.write_bytes(b"")
        assert is_binary_file(f) is True
        assert ".png" in BINARY_EXTENSIONS

    def test_text_file(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        assert is_binary_file(f) is False

    def test_null_byte_sniffing(self, tmp_path: Path):
        f = tmp_path / "blob.dat2"
        f.write_bytes(b"abc\x00def")
        assert is_binary_file(f) is True

    def test_missing_file_treated_as_binary(self, tmp_path: Path):
        assert is_binary_file(tmp_path / "nope.txt") is True
