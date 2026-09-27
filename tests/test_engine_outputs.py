"""Tests for precise own-output filtering, single-pass reads, and symlink guards."""

from pathlib import Path

import pytest

from codewrap.engine import CodeProcessorEngine
from codewrap.git import GitHelper
from codewrap.models import ScanConfig


def make_engine(root: Path, exclude_binary: bool = False, **config_kwargs) -> CodeProcessorEngine:
    config = ScanConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests", **config_kwargs)
    return CodeProcessorEngine(config, exclude_binary=exclude_binary)


class TestOwnOutputFiltering:
    def test_default_output_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context.md") is True

    def test_numbered_output_variant_ignored(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context_1.md") is True
        assert engine.is_ignored(tmp_path / f"{tmp_path.name}_context_12.md") is True

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
        assert [i.path for i in engine.excluded] == [f]

    def test_null_byte_sniffing_skipped(self, tmp_path: Path):
        engine = make_engine(tmp_path, exclude_binary=True)
        f = tmp_path / "blob.dat2"
        f.write_bytes(b"abc\x00def" * 500)
        assert engine._load_content(f) is None
        assert [i.path for i in engine.excluded] == [f]

    def test_null_byte_allowed_when_inclusion_enabled(self, tmp_path: Path):
        engine = make_engine(tmp_path, exclude_binary=False)
        f = tmp_path / "weird.txt"
        f.write_bytes(b"a\x00b")
        assert engine._load_content(f) == "a\x00b"
        assert engine.excluded == []

    def test_unreadable_file_reported(self, tmp_path: Path):
        engine = make_engine(tmp_path)
        missing = tmp_path / "gone.py"
        assert engine._load_content(missing) is None
        assert [i.path for i in engine.excluded] == [missing]


class TestExclusionReport:
    def test_legend_and_table_embedded_in_document(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "img.png").write_bytes(b"fake image")
        engine = make_engine(tmp_path, exclude_binary=True)
        engine.process()

        report = engine.output_file.read_text(encoding="utf-8")
        assert "## How to read this document" in report
        assert "`BINARY`" in report
        assert "## Excluded files" in report
        assert "| img.png | 10 B | BINARY |" in report
        # Legend comes before content, table after it.
        assert report.index("How to read") < report.index("## File: a.py") < report.index("## Excluded files")

    def test_no_legend_without_exclusions(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        engine = make_engine(tmp_path)
        engine.process()

        report = engine.output_file.read_text(encoding="utf-8")
        assert "How to read this document" not in report
        assert "Excluded files" not in report

    def test_excluded_explicit_target_reported(self, tmp_path: Path):
        secret = tmp_path / "secret.txt"
        secret.write_text("hide me", encoding="utf-8")
        engine = make_engine(tmp_path, excludes=["*.txt"])
        files, _ = engine.process()

        assert files == 0
        assert [(i.path.name, i.reason) for i in engine.excluded] == [("secret.txt", "EXCLUDED")]


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
        config = ScanConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests")
        return CodeProcessorEngine(config, exclude_binary=False)

    def test_untracked_file_included_by_default(self, tmp_path: Path):
        engine = self._make_engine(tmp_path)
        new_file = tmp_path / "brand_new.py"
        new_file.write_text("print('hi')\n", encoding="utf-8")

        files, _ = engine.process_patch([("??", new_file)])

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## File (New): brand_new.py" in report
        assert "print('hi')" in report

    def test_staged_new_file_kept(self, tmp_path: Path):
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
            GitHelper, "get_file_diff", staticmethod(lambda f: fake_diff if f.name == "edited.py" else "")
        )

        files, _ = engine.process_patch([("M", mod_file)])

        assert files == 1
        report = engine.output_file.read_text(encoding="utf-8")
        assert "## Diff: edited.py" in report

    def test_gitignored_untracked_file_skipped(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("secret/\n", encoding="utf-8")
        engine = self._make_engine(tmp_path)
        ignored_file = tmp_path / "secret" / "key.txt"
        ignored_file.parent.mkdir()
        ignored_file.write_text("token", encoding="utf-8")

        files, _ = engine.process_patch([("??", ignored_file)])

        assert files == 0


class TestUserExcludes:
    def test_exclude_glob_drops_directory_files(self, tmp_path: Path):
        (tmp_path / "lock").mkdir()
        (tmp_path / "lock" / "big.lock").write_text("x", encoding="utf-8")
        (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
        engine = make_engine(tmp_path, excludes=["lock/**"])
        assert engine.collect_all_files() == [tmp_path / "keep.py"]

    def test_exclude_pattern_matches_extension(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("hi\n", encoding="utf-8")
        engine = make_engine(tmp_path, excludes=["*.md"])
        assert engine.collect_all_files() == [tmp_path / "a.py"]

    def test_backslash_excludes_are_normalized(self, tmp_path: Path):
        """Shells on Windows may deliver exclude patterns with backslashes."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("x", encoding="utf-8")
        (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
        engine = make_engine(tmp_path, excludes=["tests\\**"])
        assert engine.collect_all_files() == [tmp_path / "keep.py"]


class TestBuiltinNoiseExclusions:
    def test_lockfiles_and_generated_assets_excluded_silently(self, tmp_path: Path):
        (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
        for noise in (
            "uv.lock",
            "Cargo.lock",
            "package-lock.json",
            "pnpm-lock.yaml",
            "go.sum",
            "vendor.min.js",
            "theme.min.css",
            "bundle.js.map",
        ):
            (tmp_path / noise).write_text("data", encoding="utf-8")
        engine = make_engine(tmp_path)

        assert engine.collect_all_files() == [tmp_path / "keep.py"]
        # Built-in noise stays out of the Excluded files report; only user -x matches are listed.
        assert engine.excluded == []

    def test_manifest_lockfile_survives_explicit_target(self, tmp_path: Path):
        """Extension filters are not affected: a '.json' folder rule still sees normal JSON."""
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        engine = make_engine(tmp_path)
        assert engine.collect_all_files() == [tmp_path / "data.json"]


class TestMaxFileSize:
    def _engine(self, root: Path, max_file_size: int) -> CodeProcessorEngine:
        config = ScanConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests")
        return CodeProcessorEngine(config, exclude_binary=False, max_file_size=max_file_size)

    def test_oversized_file_skipped_with_size(self, tmp_path: Path):
        big = tmp_path / "big.sql"
        big.write_text("x" * 100, encoding="utf-8")
        (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
        engine = self._engine(tmp_path, max_file_size=50)

        files, _ = engine.process()

        assert files == 1
        assert [(i.path.name, i.reason, i.size) for i in engine.excluded] == [("big.sql", "LARGE", 100)]
        report = engine.output_file.read_text(encoding="utf-8")
        assert "| big.sql | 100 B | LARGE |" in report
        assert "`LARGE`" in report

    def test_limit_disabled_with_zero(self, tmp_path: Path):
        f = tmp_path / "a.py"
        f.write_text("x" * 100, encoding="utf-8")
        engine = self._engine(tmp_path, max_file_size=0)

        files, _ = engine.process()

        assert files == 1
        assert engine.excluded == []


class TestSplitOutput:
    def _engine(self, root: Path, split: str) -> CodeProcessorEngine:
        config = ScanConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests", split=split)
        return CodeProcessorEngine(config, exclude_binary=False)

    def _make_files(self, root: Path) -> None:
        for name in ("a.py", "b.py", "c.py"):
            (root / name).write_text(name + "\n" * 400, encoding="utf-8")

    def test_budget_not_exceeded_keeps_single_file(self, tmp_path: Path):
        self._make_files(tmp_path)
        engine = self._engine(tmp_path, "100000")

        engine.process()

        assert engine.bundle_folder is None
        assert engine.output_file.exists()
        assert not engine.output_dir.exists()

    def test_split_writes_parts_and_manifest(self, tmp_path: Path):
        self._make_files(tmp_path)
        # Dummy tokenizer falls back to len//4, so ~100 tokens per 400-char block.
        engine = self._engine(tmp_path, "150")

        files, tokens = engine.process()

        assert files == 3
        assert tokens > 0
        assert engine.bundle_folder == engine.output_dir
        parts = sorted(engine.output_dir.glob("part_*.md"))
        assert len(parts) >= 2
        assert all("## File:" in p.read_text(encoding="utf-8") for p in parts)
        manifest = (engine.output_dir / "manifest.md").read_text(encoding="utf-8")
        assert "manifest" in manifest
        for part in parts:
            assert f"`{part.name}`" in manifest
        # No stray single-file output alongside the bundle.
        assert not engine.output_file.exists()

    def test_excess_parts_from_previous_run_are_removed(self, tmp_path: Path):
        self._make_files(tmp_path)
        (tmp_path / "big.py").write_text("y" * 4000, encoding="utf-8")
        engine = self._engine(tmp_path, "150")
        engine.process()
        stale = engine.output_dir / "part_99.md"
        stale.write_text("stale", encoding="utf-8")

        files, _ = engine.process()

        assert files == 4
        assert not stale.exists()

    def test_bundle_folder_ignored_on_rescan(self, tmp_path: Path):
        self._make_files(tmp_path)
        engine = self._engine(tmp_path, "150")
        engine.process()
        assert (engine.output_dir / "part_01.md").exists()

        engine2 = self._engine(tmp_path, "150000")
        collected = engine2.collect_all_files()

        assert sorted(p.name for p in collected) == ["a.py", "b.py", "c.py"]


class TestPerFileBundle:
    def _engine(self, root: Path) -> CodeProcessorEngine:
        config = ScanConfig(root_path=str(root), tokenizer="dummy-tokenizer-for-tests", per_file=True)
        return CodeProcessorEngine(config, exclude_binary=False)

    def test_raw_copies_with_numbered_names(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "engine.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "Makefile").write_text("all:\n", encoding="utf-8")
        engine = self._engine(tmp_path)

        files, tokens = engine.process()

        assert files == 2
        assert tokens > 0
        assert engine.bundle_folder == engine.output_dir
        assert (engine.output_dir / "001_Makefile.txt").read_text(encoding="utf-8") == "all:\n"
        assert (engine.output_dir / "002_src_engine.py.txt").read_text(encoding="utf-8") == "x = 1\n"
        # No single Markdown document and no manifest in per-file mode.
        assert not engine.output_file.exists()
        assert not (engine.output_dir / "manifest.md").exists()

    def test_stale_attachments_removed_on_rerun(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        engine = self._engine(tmp_path)
        engine.process()
        stale = engine.output_dir / "009_ghost.py.txt"
        stale.write_text("gone", encoding="utf-8")

        engine.process()

        assert not stale.exists()
        assert [p.name for p in engine.output_dir.iterdir()] == ["001_a.py.txt"]

    def test_bundle_folder_never_rescanned(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        engine = self._engine(tmp_path)
        engine.process()

        collected = engine.collect_all_files()

        assert collected == [tmp_path / "a.py"]
