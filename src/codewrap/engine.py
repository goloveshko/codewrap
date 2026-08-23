import logging
import re
from collections.abc import Callable
from pathlib import Path

import pathspec

from codewrap.git import GitHelper
from codewrap.models import PresetConfig, TargetRule
from codewrap.utils import is_binary_file

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Path, int, int], None]


class CodeProcessorEngine:
    def __init__(
        self,
        config: PresetConfig,
        execution_cwd: Path | None = None,
        exclude_binary: bool = True,
    ) -> None:
        self.config = config
        self.root_path = Path(config.root_path).resolve()
        self.execution_cwd = (execution_cwd or Path.cwd()).resolve()
        self.output_file = self._resolve_output_file()
        self._own_outputs_re = self._build_own_outputs_regex()
        self.ignore_spec = self._load_gitignore()
        self.tokenizer = self._init_tokenizer(config.encoding)
        self.exclude_binary = exclude_binary
        self.skipped_files: list[Path] = []

    @staticmethod
    def _clean_base_name(name: str) -> str:
        return re.sub(r"[^\w\-]", "_", name).strip("_")

    def _build_own_outputs_regex(self) -> re.Pattern[str] | None:
        """Compile a matcher for this engine's own generated Markdown outputs.

        Matches only files derived from the project/preset name or an explicit
        ``--output`` path, including numbered variants (e.g. 'proj_context.md',
        'proj_context_2.md', 'report_1.md'). User files that merely contain
        '_context' in their name are not affected.
        """
        parts: list[str] = []
        for candidate in (self.root_path.name, self.config.name):
            if not candidate:
                continue
            base = self._clean_base_name(candidate)
            if base:
                parts.append(rf"{re.escape(base)}_context(?:_\d+)?\.md")
        if self.config.output_file:
            p = Path(self.config.output_file)
            parts.append(rf"{re.escape(p.stem)}(?:_\d+)?{re.escape(p.suffix)}")
        combined = "|".join(dict.fromkeys(parts))
        return re.compile(combined) if combined else None

    def _resolve_output_file(self) -> Path:
        base_dir = self.execution_cwd if self.config.save_in_cwd else self.root_path

        if self.config.output_file:
            base_path = Path(self.config.output_file)
            target = base_path if base_path.is_absolute() else (base_dir / base_path)
        else:
            base_name = self.config.name if self.config.name else self.root_path.name
            clean_name = self._clean_base_name(base_name)
            target = base_dir / f"{clean_name}_context.md"

        target = target.resolve()

        if self.config.use_numbering and target.exists():
            stem = target.stem
            ext = target.suffix
            counter = 1
            while target.exists():
                target = target.parent / f"{stem}_{counter}{ext}"
                counter += 1

        return target

    def _init_tokenizer(self, encoding_name: str):
        try:
            import tiktoken

            return tiktoken.get_encoding(encoding_name)
        except ImportError:
            logger.warning("tiktoken is not installed — token counts will use a rough estimate (len / 4).")
        except Exception as e:
            logger.warning("Failed to initialize tiktoken encoding '%s' (%s) — using rough estimate.", encoding_name, e)
        return None

    def count_tokens(self, text: str) -> int:
        if self.tokenizer is not None:
            try:
                return len(self.tokenizer.encode(text, disallowed_special=()))
            except Exception as e:
                logger.debug("tiktoken encoding failed (%s); falling back to rough estimate.", e)
        return max(1, len(text) // 4)

    def _load_gitignore(self) -> pathspec.PathSpec:
        ignore_file = self.root_path / ".gitignore"
        patterns = [
            ".git/",
            ".venv/",
            "venv/",
            "__pycache__/",
            ".DS_Store",
            "node_modules/",
            "dist/",
            "build/",
            "*.pyc",
            ".codewrap.json",
        ]
        if ignore_file.exists():
            try:
                patterns.extend(ignore_file.read_text(encoding="utf-8").splitlines())
            except Exception as e:
                logger.warning("Could not read %s: %s", ignore_file, e)
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, path: Path) -> bool:
        resolved = path.resolve()

        if resolved == self.output_file or resolved.name == ".codewrap.json":
            return True

        if self._own_outputs_re is not None and self._own_outputs_re.fullmatch(resolved.name):
            return True

        if self.exclude_binary and resolved.is_file() and is_binary_file(resolved):
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

    def process_diff(self, diff_text: str) -> tuple[int, int]:
        """Generates a Markdown file containing a unified Git diff block."""
        tokens = self.count_tokens(diff_text)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Git Diff Context: {self.root_path.name}\n\n")
            f.write("```diff\n")
            f.write(diff_text)
            f.write("\n```\n")

        return 1, tokens

    def process(self, progress_callback: ProgressCallback | None = None) -> tuple[int, int]:
        files_to_process = self.collect_all_files()
        total_tokens = 0
        file_count = 0

        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Project Context: {self.root_path.name}\n\n")

            for path in files_to_process:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.warning("Skipped unreadable file: %s (%s)", path, e)
                    self.skipped_files.append(path)
                    continue

                tokens = self.count_tokens(content)
                total_tokens += tokens
                file_count += 1

                relative_path = path.relative_to(self.root_path)
                ext = path.suffix.lstrip(".")

                f.write(f"## File: {relative_path}\n")
                f.write(f"```{ext}\n")
                f.write(content)
                f.write("\n```\n\n")

                if progress_callback:
                    progress_callback(relative_path, tokens, total_tokens)

        return file_count, total_tokens

    def process_patch(
        self, status_files: list[tuple[str, Path]], progress_callback: ProgressCallback | None = None
    ) -> tuple[int, int]:
        """
        Smart Patch Processor:
        - Modified files -> Outputs 'git diff' block.
        - Staged new files ('A') -> Outputs full content block.
        - Untracked files ('??') -> Skipped by default to avoid including scratchpads/notes.
        """
        total_tokens = 0
        file_count = 0
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Smart Uncommitted Patch Context: {self.root_path.name}\n\n")

            for status_code, file_path in status_files:
                # Ignore untracked junk files (status '??')
                if status_code == "??" or self.is_ignored(file_path) or not file_path.exists():
                    continue

                rel_path = file_path.relative_to(self.root_path)

                # Staged New files ('A' / 'A ') -> Full Content
                if status_code in ("A", "A ", "AM"):
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.warning("Skipped unreadable file: %s (%s)", file_path, e)
                        self.skipped_files.append(file_path)
                        continue

                    tokens = self.count_tokens(content)
                    total_tokens += tokens
                    file_count += 1
                    ext = file_path.suffix.lstrip(".")

                    f.write(f"## File (New): {rel_path}\n")
                    f.write(f"```{ext}\n")
                    f.write(content)
                    f.write("\n```\n\n")

                    if progress_callback:
                        progress_callback(rel_path, tokens, total_tokens)
                else:
                    # Modified files -> Git Diff
                    diff_text = GitHelper.get_file_diff(self.root_path, rel_path)
                    if not diff_text.strip():
                        continue

                    tokens = self.count_tokens(diff_text)
                    total_tokens += tokens
                    file_count += 1

                    f.write(f"## Diff: {rel_path}\n")
                    f.write("```diff\n")
                    f.write(diff_text)
                    f.write("\n```\n\n")

                    if progress_callback:
                        progress_callback(rel_path, tokens, total_tokens)

        return file_count, total_tokens
