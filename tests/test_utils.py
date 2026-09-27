"""Tests for pure helper functions in codewrap.utils."""

import os
from pathlib import Path

import pytest

from codewrap.models import TargetRule
from codewrap.utils import format_size, infer_common_root, is_binary_bytes, parse_size_arg, parse_target_arg


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


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(812) == "812 B"

    def test_larger_units(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(5 * 1024 * 1024) == "5.0 MB"
        assert format_size(3 * 1024**3) == "3.0 GB"


class TestParseSizeArg:
    def test_plain_bytes(self):
        assert parse_size_arg("2048") == 2048
        assert parse_size_arg("0") == 0

    def test_units_case_insensitive(self):
        assert parse_size_arg("512kb") == 512 * 1024
        assert parse_size_arg("2MB") == 2 * 1024**2
        assert parse_size_arg("1 gb") == 1024**3

    def test_fraction(self):
        assert parse_size_arg("1.5kb") == 1536

    @pytest.mark.parametrize("bad", ["", "abc", "10 tb", "5kb2", "-1"])
    def test_invalid_raises(self, bad: str):
        with pytest.raises(ValueError):
            parse_size_arg(bad)


class TestIsBinaryBytes:
    def test_plain_text_is_not_binary(self):
        assert is_binary_bytes(b"def f():\n    return 1\n") is False

    def test_null_byte_is_binary(self):
        assert is_binary_bytes(b"abc\x00def") is True

    def test_utf8_with_multibyte_is_text(self):
        assert is_binary_bytes("héllo wörld — ünïcode ✓".encode()) is False

    def test_truncated_multibyte_tail_still_text(self):
        # A NUL-free file cut mid multibyte char must not be misclassified.
        data = "привет мир ".encode()[:-2]
        assert is_binary_bytes(data) is False

    def test_high_control_ratio_is_binary(self):
        # No NUL, but lots of non-printable control bytes.
        assert is_binary_bytes(b"\x01\x02\x03\x04" * 50) is True

    def test_empty_is_not_binary(self):
        assert is_binary_bytes(b"") is False
