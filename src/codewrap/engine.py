import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

import pathspec

from codewrap.models import ScanConfig, TargetRule
from codewrap.tokenizers import resolve_tokenizer
from codewrap.utils import BINARY_EXTENSIONS

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Path, int, int], None]


class CodeProcessorEngine:
    """Core code collection engine (decoupled from UI and CLI)."""

    def __init__(
        self,
        config: ScanConfig,
        execution_cwd: Path | None = None,
        exclude_binary: bool = True,
    ) -> None:
        self.config = config
        self.root_path = Path(config.root_path).resolve()
        self.execution_cwd = (execution_cwd or Path.cwd()).resolve()
        self.output_file = self._resolve_output_file()
        self._own_outputs_re = self._build_own_outputs_regex()
        self.ignore_spec = self._load_gitignore()
        self.encoding_name = resolve_tokenizer(config.tokenizer)
        self.tokenizer, self.estimate_reason = self._init_tokenizer(self.encoding_name)
        self.exclude_binary = exclude_binary
        self.skipped_files: list[Path] = []
        # (relative path, tokens) per emitted section, for the run summary.
        self.file_stats: list[tuple[Path, int]] = []

    @staticmethod
    def _clean_base_name(name: str) -> str:
        return re.sub(r"[^\w\-]", "_", name).strip("_")

    def _build_own_outputs_regex(self) -> re.Pattern[str] | None:
        """Compile a matcher for this engine's own generated Markdown outputs."""
        parts: list[str] = []
        base = self._clean_base_name(self.root_path.name)
        if base:
            parts.append(rf"{re.escape(base)}_context(?:_\d+)?\.md")
        if self.config.output_file:
            p = Path(self.config.output_file)
            parts.append(rf"{re.escape(p.stem)}(?:_\d+)?{re.escape(p.suffix)}")
        combined = "|".join(dict.fromkeys(parts))
        return re.compile(combined, re.IGNORECASE) if combined else None

    def _resolve_output_file(self) -> Path:
        base_dir = self.execution_cwd if self.config.save_in_current_dir else self.root_path

        if self.config.output_file:
            base_path = Path(self.config.output_file)
            target = base_path if base_path.is_absolute() else (base_dir / base_path)
        else:
            clean_name = self._clean_base_name(self.root_path.name)
            target = base_dir / f"{clean_name}_context.md"

        target = target.resolve()

        if self.config.auto_rename_outputs and target.exists():
            stem = target.stem
            ext = target.suffix
            counter = 1
            while target.exists():
                target = target.parent / f"{stem}_{counter}{ext}"
                counter += 1

        return target

    def _init_tokenizer(self, encoding_name: str) -> tuple[object | None, str | None]:
        """Create the tiktoken encoding, returning an estimate reason on failure.

        A persistent cache directory keeps encodings usable offline after the
        first successful download instead of silently degrading counts.
        """
        os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path.home() / ".codewrap" / "cache"))
        try:
            import tiktoken

            return tiktoken.get_encoding(encoding_name), None
        except ImportError:
            return None, "tiktoken is not installed"
        except Exception as e:
            return None, f"could not load encoding '{encoding_name}' ({e.__class__.__name__}: {e}); is this the first run offline?"

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self.tokenizer is not None:
            try:
                return len(self.tokenizer.encode(text, disallowed_special=()))  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("tiktoken encoding failed (%s); falling back to rough estimate.", e)
                self.estimate_reason = "tiktoken failed to encode part of the text"
        return max(1, len(text) // 4)

    def _load_content(self, path: Path) -> str | None:
        try:
            data = path.read_bytes()
        except Exception as e:
            logger.warning("Skipped unreadable file: %s (%s)", path, e)
            self.skipped_files.append(path)
            return None

        if self.exclude_binary and (path.suffix.lower() in BINARY_EXTENSIONS or b"\x00" in data[:1024]):
            self.skipped_files.append(path)
            return None

        return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    def _load_gitignore(self) -> pathspec.PathSpec:
        ignore_file = self.root_path / ".gitignore"
        # User --exclude patterns win first, then built-in defaults, then .gitignore.
        # Git-style patterns only ever use '/' separators; shells on Windows may hand
        # them over with backslashes, so normalize before compiling the spec.
        patterns = [p.replace("\\", "/") for p in self.config.excludes] + [
            ".git/",
            ".venv/",
            "venv/",
            "__pycache__/",
            ".DS_Store",
            "node_modules/",
            "dist/",
            "build/",
            "*.pyc",
        ]
        if ignore_file.exists():
            try:
                patterns.extend(ignore_file.read_text(encoding="utf-8").splitlines())
            except Exception as e:
                logger.warning("Could not read %s: %s", ignore_file, e)
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, path: Path) -> bool:
        resolved = path.resolve()

        if resolved == self.output_file:
            return True

        if self._own_outputs_re is not None and self._own_outputs_re.fullmatch(resolved.name):
            return True

        try:
            relative_path = resolved.relative_to(self.root_path)
        except ValueError:
            return True

        path_str = str(relative_path)
        if resolved.is_dir() and not path_str.endswith("/"):
            path_str += "/"

        return self.ignore_spec.match_file(path_str)

    def _collect_files_for_target(self, rule: TargetRule) -> list[Path]:
        rule_path = Path(rule.path)
        target_path = (rule_path if rule_path.is_absolute() else (self.root_path / rule_path)).resolve()

        if not target_path.exists():
            return []

        if target_path.is_file():
            return [target_path] if not self.is_ignored(target_path) else []

        allowed_exts = {e.lower().strip(".") for e in rule.extensions} if rule.extensions else None
        collected: list[Path] = []

        def recurse(current_dir: Path):
            try:
                entries = sorted(current_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError as e:
                logger.warning("Skipping directory without read permission: %s (%s)", current_dir, e)
                return

            for entry in entries:
                if entry.is_symlink():
                    logger.warning("Skipping symlink to prevent cycles: %s", entry)
                    continue

                if self.is_ignored(entry):
                    continue

                if entry.is_dir():
                    recurse(entry)
                elif entry.is_file():
                    if allowed_exts is None or entry.suffix.lower().lstrip(".") in allowed_exts:
                        collected.append(entry)

        recurse(target_path)
        return collected

    def collect_all_files(self) -> list[Path]:
        all_files: set[Path] = set()

        if not self.config.targets:
            default_rule = TargetRule(path=".")
            for f in self._collect_files_for_target(default_rule):
                all_files.add(f)
        else:
            for rule in self.config.targets:
                for f in self._collect_files_for_target(rule):
                    all_files.add(f)

        return sorted(list(all_files), key=lambda p: p.relative_to(self.root_path))

    def _finish(self, parts: list[str], file_count: int) -> tuple[int, int]:
        """Write the assembled document and count tokens over the final text, not section sums."""
        document = "".join(parts)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text(document, encoding="utf-8", newline="\n")
        return file_count, self.count_tokens(document)

    def process_diff(self, diff_text: str) -> tuple[int, int]:
        parts = [
            f"# Git Diff Context: {self.root_path.name}\n\n",
            "```diff\n",
            diff_text,
            "\n```\n",
        ]
        return self._finish(parts, 1)

    def process_patch(
        self,
        status_files: list[tuple[str, Path]],
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[int, int]:
        """Write a smart patch context: diffs for tracked changes, full content for new files."""
        from codewrap.git import GitHelper

        parts = [f"# Smart Uncommitted Patch Context: {self.root_path.name}\n\n"]
        running_tokens = 0
        file_count = 0

        for status_code, file_path in status_files:
            if self.is_ignored(file_path) or not file_path.exists():
                continue

            rel_path = file_path.relative_to(self.root_path)

            if status_code == "??" or "A" in status_code:
                content = self._load_content(file_path)
                if content is None:
                    continue

                tokens = self.count_tokens(content)
                running_tokens += tokens
                file_count += 1
                self.file_stats.append((rel_path, tokens))
                ext = file_path.suffix.lstrip(".")

                parts.append(f"## File (New): {rel_path}\n")
                parts.append(f"```{ext}\n")
                parts.append(content)
                parts.append("\n```\n\n")

                if progress_callback:
                    progress_callback(rel_path, tokens, running_tokens)
            else:
                diff_text = GitHelper.get_file_diff(file_path)
                if not diff_text.strip():
                    continue

                tokens = self.count_tokens(diff_text)
                running_tokens += tokens
                file_count += 1
                self.file_stats.append((rel_path, tokens))

                parts.append(f"## Diff: {rel_path}\n")
                parts.append("```diff\n")
                parts.append(diff_text)
                parts.append("\n```\n\n")

                if progress_callback:
                    progress_callback(rel_path, tokens, running_tokens)

        return self._finish(parts, file_count)

    def process(self, progress_callback: ProgressCallback | None = None) -> tuple[int, int]:
        files_to_process = self.collect_all_files()

        parts = [f"# Project Context: {self.root_path.name}\n\n"]
        running_tokens = 0
        file_count = 0

        for path in files_to_process:
            content = self._load_content(path)
            if content is None:
                continue

            tokens = self.count_tokens(content)
            running_tokens += tokens
            file_count += 1
            relative_path = path.relative_to(self.root_path)
            self.file_stats.append((relative_path, tokens))

            ext = path.suffix.lstrip(".")

            parts.append(f"## File: {relative_path}\n")
            parts.append(f"```{ext}\n")
            parts.append(content)
            parts.append("\n```\n\n")

            if progress_callback:
                progress_callback(relative_path, tokens, running_tokens)

        return self._finish(parts, file_count)
