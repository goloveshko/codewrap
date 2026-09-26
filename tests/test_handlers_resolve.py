"""Tests for resolve_scan_config: source selection, Git scoping, and flag pass-through.

GitHelper is monkeypatched so these stay pure unit tests without a real repository.
"""

from pathlib import Path

import pytest
import typer

from codewrap import handlers as handlers_mod
from codewrap.handlers import resolve_scan_config
from codewrap.settings import AppSettings


@pytest.fixture()
def fake_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Patch GitHelper with deterministic results anchored to tmp_path."""
    status = [("M", tmp_path / "edited.py"), ("??", tmp_path / "brand_new.py")]
    tracked = [tmp_path / "tracked.py"]
    monkeypatch.setattr(handlers_mod.GitHelper, "get_repo_root", staticmethod(lambda p: tmp_path))
    monkeypatch.setattr(handlers_mod.GitHelper, "is_git_repo", staticmethod(lambda p: True))
    monkeypatch.setattr(handlers_mod.GitHelper, "get_status_files", staticmethod(lambda p: list(status)))
    monkeypatch.setattr(handlers_mod.GitHelper, "get_tracked_files", staticmethod(lambda p: list(tracked)))
    monkeypatch.setattr(handlers_mod.GitHelper, "get_files_since", staticmethod(lambda p, s: [tmp_path / "old.py"]))
    return tmp_path


def resolve(fake_root: Path, **kwargs):
    params = dict(targets=None, files_list=None, modified=False, since=None, excludes=None, output=None)
    params.update(kwargs)
    return resolve_scan_config(fake_root, saved_settings=AppSettings(), **params)


class TestSourceSelection:
    def test_modified_includes_untracked_by_default(self, fake_git: Path):
        config = resolve(fake_git, modified=True)
        paths = [t.path for t in config.targets]
        assert str(fake_git / "brand_new.py") in paths
        assert str(fake_git / "edited.py") in paths

    def test_since_uses_log_window(self, fake_git: Path):
        config = resolve(fake_git, since="3 days ago")
        assert [t.path for t in config.targets] == [str(fake_git / "old.py")]

    def test_explicit_targets_parsed_with_ext_rules(self, fake_git: Path):
        config = resolve(fake_git, targets=["src:py", "README.md"])
        assert [(t.path, t.extensions) for t in config.targets] == [("src", ["py"]), ("README.md", [])]

    def test_files_list_read_line_by_line(self, fake_git: Path):
        lst = fake_git / "list.txt"
        lst.write_text("a.py\n# comment\nsrc:md\n", encoding="utf-8")
        config = resolve(fake_git, files_list=lst)
        assert [(t.path, t.extensions) for t in config.targets] == [("a.py", []), ("src", ["md"])]

    def test_missing_files_list_exits_with_error(self, fake_git: Path):
        with pytest.raises(typer.Exit):
            resolve(fake_git, files_list=fake_git / "nope.txt")

    def test_falls_back_to_git_tracked_files(self, fake_git: Path):
        config = resolve(fake_git)
        assert [t.path for t in config.targets] == [str(fake_git / "tracked.py")]


class TestConfigPassThrough:
    def test_excludes_and_output_propagate(self, fake_git: Path):
        config = resolve(fake_git, excludes=["tests/**"], output=Path("out.md"))
        assert config.excludes == ["tests/**"]
        assert config.output_file == "out.md"

    def test_global_settings_applied(self, fake_git: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(handlers_mod.GitHelper, "is_git_repo", staticmethod(lambda p: False))
        settings = AppSettings(copy_to_clipboard=True, auto_rename_outputs=True, tokenizer="cl100k_base")
        config = resolve_scan_config(fake_git, None, None, False, None, None, None, settings)
        assert config.copy_to_clipboard is True
        assert config.auto_rename_outputs is True
        assert config.tokenizer == "cl100k_base"
        assert config.targets == []
