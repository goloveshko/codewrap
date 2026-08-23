"""Tests for NUL-separated git porcelain parsing (review #8)."""

import subprocess
from pathlib import Path

from codewrap.git import _parse_status_z


def make_result(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")


class TestParseStatusZ:
    def test_modified_and_untracked(self, tmp_path: Path):
        res = make_result("M  a.py\0?? notes.txt\0")
        parsed = _parse_status_z(res, tmp_path)
        assert parsed == [
            ("M", tmp_path / "a.py"),
            ("??", tmp_path / "notes.txt"),
        ]

    def test_unstaged_status_code_stripped(self, tmp_path: Path):
        res = make_result(" M tracked.py\0")
        assert _parse_status_z(res, tmp_path) == [("M", tmp_path / "tracked.py")]

    def test_rename_consumes_original_path(self, tmp_path: Path):
        res = make_result("R  new_name.py\0old_name.py\0")
        assert _parse_status_z(res, tmp_path) == [("R", tmp_path / "new_name.py")]

    def test_copy_record(self, tmp_path: Path):
        res = make_result("C  copy.txt\0orig.txt\0")
        assert _parse_status_z(res, tmp_path) == [("C", tmp_path / "copy.txt")]

    def test_paths_with_spaces_and_quotes_unquoted(self, tmp_path: Path):
        res = make_result('A  "weird \\"name\\".py"\0')
        # In -z format quotes are literal characters of the filename, never wrappers.
        assert _parse_status_z(res, tmp_path) == [("A", tmp_path / '"weird \\"name\\".py"')]

    def test_short_records_skipped(self, tmp_path: Path):
        res = make_result("\0ab\0M  ok.py\0\0")
        assert _parse_status_z(res, tmp_path) == [("M", tmp_path / "ok.py")]

    def test_empty_output(self, tmp_path: Path):
        assert _parse_status_z(make_result(""), tmp_path) == []
