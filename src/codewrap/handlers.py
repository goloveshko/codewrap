from pathlib import Path

import typer
from rich.console import Console

from codewrap.engine import CodeProcessorEngine
from codewrap.git import GitHelper
from codewrap.models import PresetConfig, TargetRule
from codewrap.presets import PresetManager
from codewrap.settings import AppSettings
from codewrap.utils import infer_common_root, parse_target_arg

console = Console()


def _build_mode_config(current_folder: Path, output: Path | None, settings: AppSettings) -> PresetConfig:
    """Build a config for diff/patch modes honoring global user settings."""
    return PresetConfig(
        root_path=str(current_folder),
        output_file=str(output) if output else None,
        copy_to_clipboard=settings.copy_to_clipboard,
        use_numbering=settings.use_numbering,
        save_in_cwd=settings.save_in_cwd,
        encoding=settings.encoding,
    )


def run_diff_mode(
    current_folder: Path,
    since: str | None,
    output: Path | None,
    saved_settings: AppSettings,
) -> None:
    """Handle execution for Git Diff mode (-d/--diff)."""
    if not GitHelper.is_git_repo(current_folder):
        console.print("[red]❌ Not a Git repository! Cannot generate diff.[/red]")
        raise typer.Exit(1)

    diff_text = GitHelper.get_diff_text(current_folder, ref=since)
    if not diff_text.strip():
        console.print("[yellow]⚠️ No Git diff changes found.[/yellow]")
        raise typer.Exit(0)

    dummy_config = _build_mode_config(current_folder, output, saved_settings)
    engine = CodeProcessorEngine(dummy_config, exclude_binary=saved_settings.exclude_binary)
    _, tokens = engine.process_diff(diff_text)

    console.print(f"\n[bold green]✅ Git Diff Generated![/bold green] Tokens (≈): [cyan]{tokens}[/cyan]")
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    if saved_settings.copy_to_clipboard:
        try:
            import pyperclip

            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print("[bold green]📋 Diff copied to clipboard![/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")


def run_patch_mode(
    current_folder: Path,
    output: Path | None,
    saved_settings: AppSettings,
) -> None:
    """Handle execution for Smart Patch mode (-pt/--patch)."""
    if not GitHelper.is_git_repo(current_folder):
        console.print("[red]❌ Not a Git repository! Cannot generate patch.[/red]")
        raise typer.Exit(1)

    status_files = GitHelper.get_status_files(current_folder)
    if not status_files:
        console.print("[yellow]⚠️ No uncommitted changes or new files found.[/yellow]")
        raise typer.Exit(0)

    dummy_config = _build_mode_config(current_folder, output, saved_settings)
    engine = CodeProcessorEngine(dummy_config, exclude_binary=saved_settings.exclude_binary)

    def cli_progress(path: Path, tokens: int, total_tokens: int):
        console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")

    console.print(f"[bold blue]🛠 Generating Smart Patch for:[/bold blue] {current_folder}")
    files, tokens = engine.process_patch(status_files, progress_callback=cli_progress)

    console.print(
        f"\n[bold green]✅ Smart Patch Generated![/bold green] Items: {files} | Tokens (≈): [cyan]{tokens}[/cyan]"
    )
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    if engine.skipped_files:
        console.print(f"[yellow]⚠️ Skipped {len(engine.skipped_files)} unreadable file(s):[/yellow]")
        for skipped in engine.skipped_files:
            console.print(f"  • {skipped}")

    if saved_settings.copy_to_clipboard:
        try:
            import pyperclip

            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print("[bold green]📋 Patch copied to clipboard![/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")


def resolve_scan_config(
    current_folder: Path,
    preset: str | None,
    target: list[str] | None,
    files_list: Path | None,
    modified: bool,
    since: str | None,
    output: Path | None,
    preset_mgr: PresetManager,
    saved_settings: AppSettings,
    directory_passed: bool,
) -> PresetConfig:
    """Resolve final PresetConfig from presets, folder bindings, local configs, or Git auto-detection."""
    target_preset = preset

    # Zero-Clutter folder binding lookup
    if not target_preset and not target and not files_list and not modified and not since:
        bound_preset = saved_settings.folder_bindings.get(str(current_folder))
        if bound_preset:
            target_preset = bound_preset
            console.print(f"[dim]🔗 Auto-detected bound preset for folder: {bound_preset}[/dim]")

    if target_preset:
        config = preset_mgr.load_preset(target_preset)
        if not config:
            console.print(f"[red]❌ Preset '{target_preset}' not found in {preset_mgr.presets_dir}![/red]")
            raise typer.Exit(1)
        console.print(f"[green]Loaded preset:[/green] {target_preset}")

        if directory_passed:
            config.root_path = str(current_folder)
        if output is not None:
            config.output_file = str(output)
        return config

    # Check for local .codewrap.json file
    local_config = preset_mgr.load_local_config(current_folder)
    if local_config and not target and not files_list and not modified and not since:
        console.print("[dim]📄 Auto-loaded local config (.codewrap.json)[/dim]")
        if directory_passed:
            local_config.root_path = str(current_folder)
        if output is not None:
            local_config.output_file = str(output)
        return local_config

    rules: list[TargetRule] = []

    if modified:
        if not GitHelper.is_git_repo(current_folder):
            console.print("[red]❌ Not a Git repository![/red]")
            raise typer.Exit(1)
        # Exclude untracked '??' files
        status_files = GitHelper.get_status_files(current_folder)
        tracked_changes = [p for code, p in status_files if code != "??"]
        console.print(f"[dim]🌿 Git modified/staged files detected: {len(tracked_changes)}[/dim]")
        rules = [TargetRule(path=str(f)) for f in tracked_changes]
    elif since:
        if not GitHelper.is_git_repo(current_folder):
            console.print("[red]❌ Not a Git repository![/red]")
            raise typer.Exit(1)
        git_files = GitHelper.get_files_since(current_folder, since)
        console.print(f"[dim]🌿 Git files changed since '{since}': {len(git_files)}[/dim]")
        rules = [TargetRule(path=str(f)) for f in git_files]
    elif target:
        rules = [parse_target_arg(t) for t in target]
    elif files_list:
        fl_path = files_list if files_list.is_absolute() else current_folder / files_list
        if fl_path.exists():
            for line in fl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    rules.append(parse_target_arg(line))
    elif GitHelper.is_git_repo(current_folder):
        tracked_files = GitHelper.get_tracked_files(current_folder)
        console.print(f"[dim]🌿 Git repository auto-detected ({len(tracked_files)} tracked files)[/dim]")
        rules = [TargetRule(path=str(f)) for f in tracked_files]

    root = infer_common_root(rules, current_folder)

    return PresetConfig(
        root_path=str(root),
        targets=rules,
        output_file=str(output) if output else None,
        copy_to_clipboard=saved_settings.copy_to_clipboard,
        use_numbering=saved_settings.use_numbering,
        save_in_cwd=saved_settings.save_in_cwd,
        encoding=saved_settings.encoding,
    )
