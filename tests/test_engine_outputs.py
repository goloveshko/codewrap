"""Tests for precise own-output filtering in the engine (review #6)."""

from pathlib import Path

from codewrap.engine import CodeProcessorEngine
from codewrap.models import PresetConfig


def make_engine(root: Path, **config_kwargs) -> CodeProcessorEngine:
    config = PresetConfig(root_path=str(root), encoding="dummy-encoding-for-tests", **config_kwargs)
    return CodeProcessorEngine(config, exclude_binary=False)


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
