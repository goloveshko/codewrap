"""Tests for precise own-output filtering (review #6), single-pass reads (#14) and symlink guards (#13)."""

from pathlib import Path

import pytest

from codewrap.engine import CodeProcessorEngine
from codewrap.models import PresetConfig


def make_engine(root: Path, exclude_binary: bool = False, **config_kwargs) -> CodeProcessorEngine:
    config = PresetConfig(root_path=str(root), encoding="dummy-encoding-for-tests", **config_kwargs)
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
        """Regression for review #6: legit files like my_context.md must not be dropped."""
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


class TestCountTokens:
    def test_empty_text_zero_tokens(self, tmp_path: Path):
        """Review #16: an empty file must count as 0 tokens, not 1."""
        engine = make_engine(tmp_path)
        assert engine.count_tokens("") == 0

    def test_short_text_at_least_one_token(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.count_tokens("abc") == 1


class TestLoadContent:
    """Single-pass reading with binary exclusion (review #14)."""

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
    """Recursion must not follow symlinked directories (review #13)."""

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
