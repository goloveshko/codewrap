from pathlib import Path

import typer

from codewrap.engine import CodeProcessorEngine
from codewrap.git import GitHelper
from codewrap.models import ScanConfig, TargetRule
from codewrap.settings import AppSettings
from codewrap.ui import (
    console,
    copy_output_to_clipboard,
    print_progress,
    print_skipped_summary,
    print_token_summary,
)
from codewrap.utils import infer_common_root, parse_target_arg


def _build_config(current_folder: Path, output: Path | None, settings: AppSettings, **overrides) -> ScanConfig:
    """Build a scan config honoring global user settings plus per-mode overrides."""
    return ScanConfig(
        root_path=str(current_folder),
        output_file=str(output) if output else None,
        copy_to_clipboard=settings.copy_to_clipboard,
        auto_rename_outputs=settings.auto_rename_outputs,
        save_in_current_dir=settings.save_in_current_dir,
        tokenizer=settings.tokenizer,
        **overrides,
    )


def _require_git_repo(current_folder: Path) -> None:
    """Exit with an error when the folder is not inside a Git repository."""
    if GitHelper.get_repo_root(current_folder) is None:
        console.print("[red]❌ Not a Git repository![/red]")
        raise typer.Exit(1)


def run_diff_since_mode(
    current_folder: Path,
    since: str,
    output: Path | None,
    excludes: list[str] | None,
    saved_settings: AppSettings,
) -> None:
    """Handle '-d -s <date>': unified diff against the last commit before that date."""
    _require_git_repo(current_folder)

    ref = GitHelper.resolve_date_ref(current_folder, since)
    if ref is None:
        console.print(f"[red]❌ Could not resolve a commit for date '{since}'.[/red]")
        raise typer.Exit(1)
    console.print(f"[dim]🕒 Diffing against commit from '{since}': {ref[:8]}[/dim]")

    diff_text = GitHelper.get_diff_text(current_folder, ref=ref)
    if diff_text is None:
        console.print("[red]❌ Git diff command failed (see warnings above).[/red]")
        raise typer.Exit(1)
    if not diff_text.strip():
        console.print("[yellow]⚠️ No Git diff changes found.[/yellow]")
        raise typer.Exit(0)

    config = _build_config(current_folder, output, saved_settings, excludes=excludes or [])
    engine = CodeProcessorEngine(config, exclude_binary=saved_settings.exclude_binary)
    _, tokens = engine.process_diff(diff_text)

    print_token_summary("✅ Git Diff Generated!", tokens, engine.encoding_name, engine.estimate_reason)
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    if engine.config.copy_to_clipboard:
        copy_output_to_clipboard(engine.output_file, label="Diff")


def run_smart_diff_mode(
    current_folder: Path,
    output: Path | None,
    excludes: list[str] | None,
    saved_settings: AppSettings,
) -> None:
    """Handle '-d': diffs for modified files, full content for new/untracked files."""
    _require_git_repo(current_folder)

    status_files = GitHelper.get_status_files(current_folder)
    if not status_files:
        console.print("[yellow]⚠️ No uncommitted changes or new files found.[/yellow]")
        raise typer.Exit(0)

    config = _build_config(current_folder, output, saved_settings, excludes=excludes or [])
    engine = CodeProcessorEngine(config, exclude_binary=saved_settings.exclude_binary)

    console.print(f"[bold blue]🛠 Generating smart diff for:[/bold blue] {current_folder}")
    files, tokens = engine.process_patch(status_files, progress_callback=print_progress)

    print_token_summary(f"✅ Smart Diff Generated! Items: {files} |", tokens, engine.encoding_name, engine.estimate_reason)
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    print_skipped_summary(engine.skipped_files)

    if engine.config.copy_to_clipboard:
        copy_output_to_clipboard(engine.output_file, label="Diff")


def resolve_scan_config(
    current_folder: Path,
    targets: list[str] | None,
    files_list: Path | None,
    modified: bool,
    since: str | None,
    excludes: list[str] | None,
    output: Path | None,
    saved_settings: AppSettings,
) -> ScanConfig:
    """Resolve the final ScanConfig from explicit targets, Git modes, or auto-detection."""
    rules: list[TargetRule] = []
    git_scoped = False

    if modified:
        _require_git_repo(current_folder)
        status_files = GitHelper.get_status_files(current_folder)
        changed_files = [p for _, p in status_files]
        console.print(f"[dim]🌿 Git modified/new files detected: {len(changed_files)}[/dim]")
        rules = [TargetRule(path=str(f)) for f in changed_files]
        git_scoped = True
    elif since:
        _require_git_repo(current_folder)
        git_files = GitHelper.get_files_since(current_folder, since)
        console.print(f"[dim]🌿 Git files changed since '{since}': {len(git_files)}[/dim]")
        rules = [TargetRule(path=str(f)) for f in git_files]
        git_scoped = True
    elif targets:
        rules = [parse_target_arg(t) for t in targets]
    elif files_list:
        fl_path = files_list if files_list.is_absolute() else current_folder / files_list
        if not fl_path.exists():
            console.print(f"[red]❌ Files list not found: {fl_path}[/red]")
            raise typer.Exit(1)
        for line in fl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rules.append(parse_target_arg(line))
    elif GitHelper.is_git_repo(current_folder):
        tracked_files = GitHelper.get_tracked_files(current_folder)
        console.print(f"[dim]🌿 Git repository auto-detected ({len(tracked_files)} tracked files)[/dim]")
        rules = [TargetRule(path=str(f)) for f in tracked_files]
        git_scoped = True

    # Git-derived scans stay anchored to the invocation folder so the report
    # is saved next to it even when the repository root sits higher up.
    root = current_folder.resolve() if git_scoped else infer_common_root(rules, current_folder)

    return _build_config(root, output, saved_settings, targets=rules, excludes=excludes or [])
