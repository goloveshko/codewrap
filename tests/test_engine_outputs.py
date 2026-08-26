"""Tests for precise own-output filtering, single-pass reads, and symlink guards."""

from pathlib import Path

import pytest

from codewrap.engine import CodeProcessorEngine
from codewrap.git import GitHelper
from codewrap.models import PresetConfig


def make_engine(root: Path, exclude_binary: bool = False, **config_kwargs) -> CodeProcessorEngine:
    config = PresetConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests", **config_kwargs)
    return CodeProcessorEngine(config, exclude_binary=exclude_binary)


class TestOwnOutputFiltering:
    def test_default_output_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context.md") is True

    def test_numbered_output_variant_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context_1.md") is True
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context_12.md") is True

    def test_preset_name_output_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path, name="api docs")
        assert engine.is_ignored(tmp_path / "api_docs_context.md") is True

    def test_user_context_named_file_kept(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.is_ignored(tmp_path / "my_context.md") is False
        assert engine.is_ignored(tmp_path / "notes_context.md") is False

    def test_custom_output_and_numbered_variants_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path, output_file=str(tmp_path / "report.md"))
        assert engine.output_file == (tmp_path / "report.md").resolve()
        assert engine.is_ignored(tmp_path / "report.md") is True
        assert engine.is_ignored(tmp_path / "report_2.md") is True
        assert engine.is_ignored(tmp_path / "other.md") is False


class TestOutputResolution:
    def test_default_output_name_sanitized(self, tmp_path: Path):
        root = tmp_path / "my cool project!"
        root.mkdir()
        engine = make_engine(root)
        assert engine.output_file == (root / "my_cool_project_context.md").resolve()

    def test_relative_output_resolved_against_root(self, tmp_path: Path):
        engine = make_engine(tmp_path, output_file="out/result.md")
        assert engine.output_file == (tmp_path / "out" / "result.md").resolve()

    def test_auto_rename_outputs_increments(self, tmp_path: Path):
        default_out = tmp_path / f"{tmp_path.name}_context.md"
        default_out.write_text("existing")
        engine = make_engine(tmp_path, auto_rename_outputs=True)
        assert engine.output_file == (tmp_path / f"{tmp_path.name}_context_1.md").resolve()


class TestCountTokens:
    def test_empty_text_zero_tokens(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.count_tokens("") == 0

    def test_short_text_at_least_one_token(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.count_tokens("abc") == 1


class TestLoadContent:
    def test_text_file_content_returned(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        f = tmp_path / "code.py"
        f.write_text("print(1)\n", encoding="utf-8")
        assert engine._load_content(f) == "print(1)\n"

    def test_binary_extension_skipped(self, tmp_path: Path):
        engine = make_engine(tmp_path, exclude_binary=True)
        f = tmp_path / "logo.png"
        f.write_bytes(b"not really a png")
        assert engine._load_content(f) is None
        assert engine.skipped_files == [f]

    def test_null_byte_sniffing_skipped(self, tmp_path: Path):
        engine = make_engine(tmp_path, exclude_binary=True)
        f = tmp_path / "blob.dat2"
        f.write_bytes(b"abc\x00def" * 500)
        assert engine._load_content(f) is None
        assert engine.skipped_files == [f]

    def test_null_byte_allowed_when_inclusion_enabled(self, tmp_path: Path):
        engine = make_engine(tmp_path, exclude_binary=False)
        f = tmp_path / "weird.txt"
        f.write_bytes(b"a\x00b")
        assert engine._load_content(f) == "a\x00b"
        assert engine.skipped_files == []

    def test_unreadable_file_reported(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        missing = tmp_path / "gone.py"
        assert engine._load_content(missing) is None
        assert engine.skipped_files == [missing]


class TestSymlinkGuard:
    def test_symlink_loop_terminates_and_not_collected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n", encoding="utf-8")
        try:
            (src / "loop").symlink_to(src, target_is_directory=True)
        except OSError:
            pytest.skip("Symlink creation not permitted on this system")

        engine = make_engine(tmp_path)
        files = engine.collect_all_files()
        assert files == [src / "a.py"]


class TestPatchModeUntracked:
    def _make_engine(self, root: Path) -> CodeProcessorEngine:
        config = PresetConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests")
        return CodeProcessorEngine(config, exclude_binary=False)

    def test_untracked_file_skipped_by_default(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        new_file = tmp_path / "brand_new.py"
        new_file.write_text("print('hi')\n", encoding="utf-8")

        files, _ = engine.process_patch([("??", new_file)])

        assert files == 0
        report = engine.output_file.read_text(encoding="utf-8")
        assert "brand_new.py" not in report

    def test_untracked_file_included_when_requested(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        new_file = tmp_path / "brand_new.py"
        new_file.write_text("print('hi')\n", encoding="utf-8")

        files, _ = engine.process_patch([("??", new_file)], include_untracked=True)

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## File (New): brand_new.py" in report
        assert "print('hi')" in report

    def test_staged_new_file_kept_without_flag(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        staged_file = tmp_path / "staged.py"
        staged_file.write_text("y = 2\n", encoding="utf-8")

        files, _ = engine.process_patch([("A", staged_file)])

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## File (New): staged.py" in report

    def test_modified_file_still_uses_diff(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        engine = self._make_engine(tmp_path)
        mod_file = tmp_path / "edited.py"
        mod_file.write_text("x = 2\n", encoding="utf-8")
        fake_diff = "--- a/edited.py\n+++ b/edited.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        monkeypatch.setattr(
            GitHelper, "get_file_diff", staticmethod(lambda repo, rel: fake_diff if rel.name == "edited.py" else "")
        )

        files, _ = engine.process_patch([("M", mod_file)])

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## Diff: edited.py" in report

    def test_gitignored_untracked_file_skipped_even_with_flag(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("secret/\n", encoding="utf-8")
        engine = self._make_engine(tmp_path)
        ignored_file = tmp_path / "secret" / "key.txt"
        ignored_file.parent.mkdir()
        ignored_file.write_text("token", encoding="utf-8")

        files, _ = engine.process_patch([("??", ignored_file)], include_untracked=True)

        assert files == 0
