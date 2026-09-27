import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

import pathspec

from codewrap.models import ScanConfig, TargetRule
from codewrap.tokenizers import resolve_tokenizer
from codewrap.utils import BINARY_EXTENSIONS, format_size, is_binary_bytes, parse_split_arg

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Path, int, int], None]

# Reason codes shown in the document legend and the 'Excluded files' table.
SKIP_BINARY = "BINARY"
SKIP_EXCLUDED = "EXCLUDED"
SKIP_LARGE = "LARGE"
SKIP_TINY = "TINY"
SKIP_UNREADABLE = "UNREADABLE"

_EXCLUSION_LEGEND = (
    "## How to read this document\n\n"
    "Each included file is a fenced code block titled `## File: <path>` "
    "(or `## Diff: <path>` in diff exports). Some candidate files were intentionally not included; "
    "they are listed at the end under **Excluded files** with a reason code:\n\n"
    "- `BINARY` — binary or media asset file\n"
    "- `EXCLUDED` — matched `.gitignore` or an `--exclude` pattern\n"
    "- `LARGE` — file exceeds the configured maximum size limit\n"
    "- `TINY` — file is below the minimum size worth including (empty or trivial one-liner)\n"
    "- `UNREADABLE` — the file could not be read from disk\n\n"
)


class ExcludedFile:
    """A candidate file that was reported but not embedded in the output."""

    __slots__ = ("path", "size", "reason")

    def __init__(self, path: Path, size: int, reason: str) -> None:
        self.path = path
        self.size = size
        self.reason = reason

    @property
    def size_display(self) -> str:
        return format_size(self.size)


class CodeProcessorEngine:
    """Core code collection engine (decoupled from UI and CLI)."""

    def __init__(
        self,
        config: ScanConfig,
        execution_cwd: Path | None = None,
        exclude_binary: bool = True,
        max_file_size: int = 0,
        min_file_size: int = 0,
    ) -> None:
        self.config = config
        self.root_path = Path(config.root_path).resolve()
        self.execution_cwd = (execution_cwd or Path.cwd()).resolve()
        self.output_file = self._resolve_output_file()
        self._own_outputs_re = self._build_own_outputs_regex()
        self.ignore_spec = self._load_gitignore()
        self.user_exclude_spec = self._compile_user_excludes()
        self.encoding_name = resolve_tokenizer(config.tokenizer)
        self.tokenizer, self.estimate_reason = self._init_tokenizer(self.encoding_name)
        self.exclude_binary = exclude_binary
        self.max_file_size = max_file_size
        self.min_file_size = min_file_size
        self.split_amount, self.split_unit = parse_split_arg(config.split) if config.split else (0, "tokens")
        self.output_dir = self.output_file.parent / self.output_file.stem
        self.bundle_folder: Path | None = None
        self.excluded: list[ExcludedFile] = []
        # (relative path, tokens) per emitted section, for the run summary.
        self.file_stats: list[tuple[Path, int, int]] = []

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
            return (
                None,
                f"could not load encoding '{encoding_name}' ({e.__class__.__name__}: {e}); is this the first run offline?",
            )

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

    def _record_excluded(self, path: Path, reason: str, size: int | None = None) -> None:
        if size is None:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
        self.excluded.append(ExcludedFile(path, size, reason))

    @staticmethod
    def _size_on_disk(path: Path, text: str) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return len(text.encode("utf-8"))

    def _load_content(self, path: Path) -> str | None:
        if self.max_file_size > 0:
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            # Checked before reading so huge files never hit memory.
            if size is not None and size > self.max_file_size:
                self._record_excluded(path, SKIP_LARGE, size=size)
                return None

        try:
            data = path.read_bytes()
        except Exception as e:
            logger.warning("Skipped unreadable file: %s (%s)", path, e)
            self._record_excluded(path, SKIP_UNREADABLE, size=0)
            return None

        # Tiny files carry no signal for an LLM; empty ones always, even with the floor disabled.
        if not data or len(data) < self.min_file_size:
            self._record_excluded(path, SKIP_TINY, size=len(data))
            return None

        if self.exclude_binary and (path.suffix.lower() in BINARY_EXTENSIONS or is_binary_bytes(data)):
            self._record_excluded(path, SKIP_BINARY, size=len(data))
            return None

        return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _normalize_excludes(patterns: list[str]) -> list[str]:
        # Git-style patterns only ever use '/' separators; shells on Windows may hand
        # them over with backslashes, so normalize before compiling a spec.
        return [p.replace("\\", "/") for p in patterns]

    def _compile_user_excludes(self) -> pathspec.PathSpec:
        return pathspec.PathSpec.from_lines("gitwildmatch", self._normalize_excludes(self.config.excludes))

    def _load_gitignore(self) -> pathspec.PathSpec:
        ignore_file = self.root_path / ".gitignore"
        # User --exclude patterns win first, then built-in defaults, then .gitignore.
        patterns = self._normalize_excludes(self.config.excludes) + [
            ".git/",
            ".venv/",
            "venv/",
            "__pycache__/",
            ".DS_Store",
            "node_modules/",
            "dist/",
            "build/",
            "*.pyc",
            # Dependency lockfiles and generated web artifacts carry no signal for an LLM.
            "*.lock",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "pnpm-lock.yaml",
            "go.sum",
            "*.min.js",
            "*.min.css",
            "*.map",
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

        # Never ingest a previous bundle (folder parts, manifest or per-file attachments).
        if (self.split_amount or self.config.per_file) and (
            resolved == self.output_dir or self.output_dir in resolved.parents
        ):
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

    def _matches_user_exclude(self, path: Path) -> bool:
        """True when a path under the root matched an explicit --exclude pattern."""
        try:
            relative_path = path.relative_to(self.root_path)
        except ValueError:
            return False
        return self.user_exclude_spec.match_file(str(relative_path))

    def _collect_files_for_target(self, rule: TargetRule) -> list[Path]:
        rule_path = Path(rule.path)
        target_path = (rule_path if rule_path.is_absolute() else (self.root_path / rule_path)).resolve()

        if not target_path.exists():
            return []

        if target_path.is_file():
            if self.is_ignored(target_path):
                self._record_excluded(target_path, SKIP_EXCLUDED)
                return []
            return [target_path]

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
                    # Report only deliberate --exclude skips here; .gitignore and
                    # built-in pruning stay silent to keep the table meaningful.
                    if entry.is_file() and self._matches_user_exclude(entry):
                        self._record_excluded(entry, SKIP_EXCLUDED)
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

    def _exclusion_table(self) -> str:
        if not self.excluded:
            return ""
        rows = []
        for item in self.excluded:
            try:
                shown = item.path.relative_to(self.root_path)
            except ValueError:
                shown = item.path
            rows.append(f"| {shown} | {format_size(item.size)} | {item.reason} |")
        return "## Excluded files\n\n| File | Size | Reason |\n| --- | --- | --- |\n" + "\n".join(rows) + "\n"

    @property
    def result_location(self) -> Path:
        """Where the user should look for the result: the bundle folder, or the single file."""
        return self.bundle_folder or self.output_file

    def _measure_unit(self, text: str) -> int:
        if self.split_unit == "bytes":
            return len(text.encode("utf-8"))
        return self.count_tokens(text)

    def _pack_blocks(self, title: str, blocks: list[str], fixed_overhead: str) -> list[list[str]]:
        """Greedy-pack file blocks into parts that fit the split budget."""
        overhead = self._measure_unit(f"# {title} (part 999 of 999)\n\n" + fixed_overhead)
        parts: list[list[str]] = [[]]
        current = overhead
        for block in blocks:
            cost = self._measure_unit(block)
            if parts[-1] and current + cost > self.split_amount:
                parts.append([])
                current = overhead
            parts[-1].append(block)
            current += cost
        return parts

    def _write_parts(
        self, title: str, parts: list[list[str]], legend: str, table: str, file_count: int
    ) -> tuple[int, int]:
        """Write budgeted parts plus a manifest into the bundle folder; returns (files, total tokens)."""
        folder = self.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        self.bundle_folder = folder
        # Drop stale parts from previous runs so the folder only ever holds the current bundle.
        for stale in list(folder.glob("part_*.md")) + [folder / "manifest.md"]:
            stale.unlink(missing_ok=True)

        total_tokens = 0
        rows: list[str] = []
        for index, part in enumerate(parts, start=1):
            document = f"# {title} (part {index} of {len(parts)})\n\n" + legend + "".join(part) + "\n" + table
            path = folder / f"part_{index:02d}.md"
            path.write_text(document, encoding="utf-8", newline="\n")
            tokens = self.count_tokens(document)
            total_tokens += tokens
            rows.append(
                f"| {index} | `{path.name}` | {len(part)} | {tokens:,} | {format_size(len(document.encode('utf-8')))} |"
            )

        manifest = (
            f"# {title} — manifest\n\n"
            f"Split into {len(parts)} parts (budget: {self.split_amount:,} "
            f"{'tokens' if self.split_unit == 'tokens' else 'bytes'} per part). "
            "Paste the parts into the chat one by one, in order.\n\n"
            "| Part | File | Blocks | Tokens | Size |\n| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
        )
        (folder / "manifest.md").write_text(manifest, encoding="utf-8", newline="\n")
        return file_count, total_tokens

    def _doc_index_section(self) -> str:
        """Compact table of contents for the single-document output (number, path, size, tokens)."""
        total = sum(size for _, _, size in self.file_stats)
        lines = [
            f"## File index ({len(self.file_stats)} files, {format_size(total)} total)",
            "One section per file follows, in this order: 'NNN path size tokens'.",
            "",
        ]
        lines += [
            f"{i:03d}  {path.as_posix()}  {format_size(size)}  {tokens:,} tok"
            for i, (path, tokens, size) in enumerate(self.file_stats, 1)
        ]
        return "\n".join(lines) + "\n\n"

    def _finish(self, title: str, blocks: list[str], file_count: int) -> tuple[int, int]:
        """Write the assembled document(s) and count tokens over the final text, not block sums."""
        legend = _EXCLUSION_LEGEND if self.excluded else ""
        table = self._exclusion_table()

        if self.split_amount:
            parts = self._pack_blocks(title, blocks, legend + "\n" + table)
            if len(parts) > 1:
                return self._write_parts(title, parts, legend, table, file_count)
            # Collapsed to one part: fall through to the normal single-document write.
            index = ""
        else:
            index = self._doc_index_section() if file_count > 1 else ""

        document = f"# {title}\n\n" + index + legend + "".join(blocks) + "\n" + table
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text(document, encoding="utf-8", newline="\n")
        return file_count, self.count_tokens(document)

    def process_diff(self, diff_text: str) -> tuple[int, int]:
        blocks = ["```diff\n" + diff_text + "\n```\n"]
        return self._finish(f"Git Diff Context: {self.root_path.name}", blocks, 1)

    def process_patch(
        self,
        status_files: list[tuple[str, Path]],
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[int, int]:
        """Write a smart patch context: diffs for tracked changes, full content for new files."""
        from codewrap.git import GitHelper

        blocks: list[str] = []
        running_tokens = 0
        file_count = 0

        for status_code, file_path in status_files:
            if self.is_ignored(file_path):
                self._record_excluded(file_path, SKIP_EXCLUDED)
                continue
            if not file_path.exists():
                self._record_excluded(file_path, SKIP_UNREADABLE, size=0)
                continue

            rel_path = file_path.relative_to(self.root_path)

            if status_code == "??" or "A" in status_code:
                content = self._load_content(file_path)
                if content is None:
                    continue

                tokens = self.count_tokens(content)
                running_tokens += tokens
                file_count += 1
                self.file_stats.append((rel_path, tokens, self._size_on_disk(file_path, content)))
                ext = file_path.suffix.lstrip(".")

                blocks.append(f"## File (New): {rel_path}\n```{ext}\n{content}\n```\n\n")

                if progress_callback:
                    progress_callback(rel_path, tokens, running_tokens)
            else:
                diff_text = GitHelper.get_file_diff(file_path)
                if not diff_text.strip():
                    continue

                tokens = self.count_tokens(diff_text)
                running_tokens += tokens
                file_count += 1
                self.file_stats.append((rel_path, tokens, len(diff_text.encode("utf-8"))))

                blocks.append(f"## Diff: {rel_path}\n```diff\n{diff_text}\n```\n\n")

                if progress_callback:
                    progress_callback(rel_path, tokens, running_tokens)

        return self._finish(f"Smart Uncommitted Patch Context: {self.root_path.name}", blocks, file_count)

    def _process_per_file(self, progress_callback: ProgressCallback | None = None) -> tuple[int, int]:
        """Copy each collected file into the bundle folder as an independent attachment.

        Names are 'NNN_<path-with-underscores>.<original ext>.txt' so upload order is kept,
        the source location stays recognizable, real file sizes are visible at a glance and
        chat UIs that only accept plain text still take the file.
        """
        folder = self.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        self.bundle_folder = folder
        # Drop numbered attachments from previous runs so the folder only holds the current bundle.
        for stale in folder.glob("[0-9][0-9][0-9]_*"):
            stale.unlink(missing_ok=True)

        file_count = 0
        running_tokens = 0
        total_tokens = 0
        total_bytes = 0
        # Ordered by scan (sorted path) order: parent folder -> [(number, file name, size)]
        index_entries: dict[str, list[tuple[int, str, int]]] = {}

        for path in self.collect_all_files():
            content = self._load_content(path)
            if content is None:
                continue

            file_count += 1
            relative_path = path.relative_to(self.root_path)
            name = f"{file_count:03d}_" + "_".join(relative_path.parts) + ".txt"
            tokens = self.count_tokens(content)
            running_tokens += tokens
            total_tokens += tokens
            size = self._size_on_disk(path, content)
            self.file_stats.append((relative_path, tokens, size))
            total_bytes += size
            index_entries.setdefault(relative_path.parent.as_posix(), []).append((file_count, relative_path.name, size))

            (folder / name).write_text(content, encoding="utf-8", newline="\n")

            if progress_callback:
                progress_callback(relative_path, tokens, running_tokens)

        if file_count:
            (folder / "000_index.txt").write_text(
                self._render_index(index_entries, file_count, total_bytes), encoding="utf-8", newline="\n"
            )

        return file_count, total_tokens

    @staticmethod
    def _render_index(entries: dict[str, list[tuple[int, str, int]]], file_count: int, total_bytes: int) -> str:
        width = max(len(name) for items in entries.values() for _, name, _ in items)
        lines = [
            f"Attachment index - {file_count} files, {format_size(total_bytes)} total.",
            "Each file is copied as NNN_<path>.<ext>.txt; paste or upload attachments in numeric order.",
            "",
        ]
        for parent, items in entries.items():
            indent = "" if parent == "." else "  "
            if indent:
                lines.append(f"{parent}/")
            lines.extend(f"{indent}{n:03d}  {name:<{width}}  {format_size(size)}" for n, name, size in items)
            if indent:
                lines.append("")
        # Drop one trailing blank line between groups, keep a single newline at EOF.
        return "\n".join(lines).rstrip("\n") + "\n"

    def process(self, progress_callback: ProgressCallback | None = None) -> tuple[int, int]:
        if self.config.per_file:
            return self._process_per_file(progress_callback)

        files_to_process = self.collect_all_files()

        blocks: list[str] = []
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
            self.file_stats.append((relative_path, tokens, self._size_on_disk(path, content)))

            ext = path.suffix.lstrip(".")

            blocks.append(f"## File: {relative_path}\n```{ext}\n{content}\n```\n\n")

            if progress_callback:
                progress_callback(relative_path, tokens, running_tokens)

        return self._finish(f"Project Context: {self.root_path.name}", blocks, file_count)
