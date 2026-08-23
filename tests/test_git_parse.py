"""Tests for NUL-separated git porcelain parsing (review #8) and diff semantics (review #11)."""

import subprocess
from pathlib import Path

import pytest

from codewrap.git import GitHelper, _parse_status_z


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


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "test@example.com", cwd=tmp_path)
    _git("config", "user.name", "tester", cwd=tmp_path)
    return tmp_path


class TestGetDiffText:
    def test_includes_staged_changes_without_ref(self, git_repo: Path):
        """Regression for review #11: bare 'git diff' missed staged changes."""
        f = git_repo / "a.txt"
        f.write_text("hello\n", encoding="utf-8")
        _git("add", ".", cwd=git_repo)
        _git("commit", "-m", "init", cwd=git_repo)
        f.write_text("changed\n", encoding="utf-8")
        _git("add", ".", cwd=git_repo)

        diff = GitHelper.get_diff_text(git_repo)
        assert "changed" in diff

    def test_explicit_ref(self, git_repo: Path):
        f = git_repo / "a.txt"
        f.write_text("v1\n", encoding="utf-8")
        _git("add", ".", cwd=git_repo)
        _git("commit", "-m", "c1", cwd=git_repo)
        f.write_text("v2\n", encoding="utf-8")

        diff = GitHelper.get_diff_text(git_repo, ref="HEAD")
        assert "v2" in diff
        assert GitHelper.get_diff_text(git_repo, ref="--cached") is not None

    def test_fallback_in_repo_without_commits(self, git_repo: Path):
        f = git_repo / "new.txt"
        f.write_text("fresh content\n", encoding="utf-8")
        _git("add", ".", cwd=git_repo)

        diff = GitHelper.get_diff_text(git_repo)
        assert "fresh content" in diff
