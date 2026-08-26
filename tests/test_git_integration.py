"""Integration tests: GitHelper must scope results to the invocation folder
while resolving paths correctly against the repository top level."""

import shutil
import subprocess
from pathlib import Path

import pytest

from codewrap.engine import CodeProcessorEngine
from codewrap.git import GitHelper
from codewrap.models import PresetConfig

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo_with_subdir(tmp_path: Path) -> Path:
    _run_git(tmp_path, "init", "-q")
    _run_git(tmp_path, "config", "user.email", "test@test.local")
    _run_git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "root.txt").write_text("root v1\n", encoding="utf-8")
    subdir = tmp_path / "scripts"
    subdir.mkdir()
    (subdir / "build.bat").write_text("echo v1\n", encoding="utf-8")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-qm", "init")
    return tmp_path


class TestFolderScoping:
    def test_repo_root_detected_from_subdirectory(self, repo_with_subdir: Path):
        subdir = repo_with_subdir / "scripts"
        assert GitHelper.get_repo_root(subdir) == repo_with_subdir.resolve()

    def test_status_from_subdir_scoped_to_that_folder(self, repo_with_subdir: Path):
        subdir = repo_with_subdir / "scripts"
        (repo_with_subdir / "root.txt").write_text("root v2\n", encoding="utf-8")
        (subdir / "build.bat").write_text("echo v2\n", encoding="utf-8")

        status = GitHelper.get_status_files(subdir)

        paths = [p for _, p in status]
        assert paths == [subdir / "build.bat"]
        assert all(p.is_absolute() for p in paths)

    def test_status_from_root_covers_whole_repo(self, repo_with_subdir: Path):
        (repo_with_subdir / "root.txt").write_text("root v2\n", encoding="utf-8")
        (repo_with_subdir / "scripts" / "build.bat").write_text("echo v2\n", encoding="utf-8")

        paths = [p for _, p in GitHelper.get_status_files(repo_with_subdir)]

        assert (repo_with_subdir / "root.txt") in paths
        assert (repo_with_subdir / "scripts" / "build.bat") in paths

    def test_file_diff_accepts_absolute_path_from_anywhere(self, repo_with_subdir: Path):
        target = repo_with_subdir / "scripts" / "build.bat"
        target.write_text("echo v2\n", encoding="utf-8")

        diff = GitHelper.get_file_diff(target)

        assert "+echo v2" in diff

    def test_diff_text_scoped_to_subfolder(self, repo_with_subdir: Path):
        (repo_with_subdir / "root.txt").write_text("root v2\n", encoding="utf-8")
        (repo_with_subdir / "scripts" / "build.bat").write_text("echo v2\n", encoding="utf-8")

        scoped = GitHelper.get_diff_text(repo_with_subdir / "scripts")

        assert "build.bat" in scoped
        assert "root.txt" not in scoped

    def test_tracked_files_scoped_to_subfolder(self, repo_with_subdir: Path):
        tracked = GitHelper.get_tracked_files(repo_with_subdir / "scripts")
        assert tracked == [(repo_with_subdir / "scripts" / "build.bat")]

    def test_patch_mode_from_subdir_includes_only_local_changes(self, repo_with_subdir: Path):
        subdir = repo_with_subdir / "scripts"
        (repo_with_subdir / "root.txt").write_text("root v2\n", encoding="utf-8")
        (subdir / "build.bat").write_text("echo v2\n", encoding="utf-8")

        config = PresetConfig(root_path=str(subdir), tokenizer="dummy-tokenizer-for-tests")
        engine = CodeProcessorEngine(config)
        status = GitHelper.get_status_files(subdir)

        files, _ = engine.process_patch(status)

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## Diff: build.bat" in report
        assert "root.txt" not in report
