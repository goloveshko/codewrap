from pathlib import Path
from typing import List, Optional
from rich.console import Console
import typer

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    help="CodeWrap: Professional LLM context gatherer for source code bases.",
    add_completion=False,
    context_settings=CONTEXT_SETTINGS,
)
config_app = typer.Typer(
    help="Manage global CodeWrap settings.",
    context_settings=CONTEXT_SETTINGS,
)
app.add_typer(config_app, name="config")

console = Console()


def parse_target_arg(target_str: str) -> TargetRule:
    from codewrap.models import TargetRule

    target_str = target_str.strip()
    last_colon = target_str.rfind(":")
    if last_colon > 1:
        exts_part = target_str[last_colon + 1 :].strip()
        if "/" not in exts_part and "\\" not in exts_part:
            path_part = target_str[:last_colon].strip()
            exts = [e.strip() for e in exts_part.split(",") if e.strip()]
            return TargetRule(path=path_part, extensions=exts)
    return TargetRule(path=target_str)


def infer_common_root(rules: list, default_root: Path) -> Path:
    abs_paths: List[Path] = []
    for r in rules:
        p = Path(r.path)
        if p.is_absolute():
            abs_paths.append(p)

    if not abs_paths:
        return default_root.resolve()

    common = abs_paths[0].parent if abs_paths[0].is_file() else abs_paths[0]
    for p in abs_paths[1:]:
        p_dir = p.parent if p.is_file() else p
        while not str(p_dir).lower().startswith(str(common).lower()):
            common = common.parent
            if common == common.parent:
                break
    return common.resolve()


@config_app.command("show")
def config_show() -> None:
    """Show current global settings."""
    from codewrap.settings import SettingsManager

    mgr = SettingsManager()
    settings = mgr.load()
    console.print("[bold blue]Current Global Settings:[/bold blue]")
    console.print(settings.model_dump_json(indent=2))


@config_app.command("set")
def config_set(
    encoding: Optional[str] = typer.Option(
        None, help="Default tokenizer encoding (e.g. o200k_base, cl100k_base)"
    ),
    exclude_binary: Optional[bool] = typer.Option(
        None, help="Auto-exclude binary files"
    ),
    numbered: Optional[bool] = typer.Option(
        None, help="Auto-number duplicate output files"
    ),
    cwd: Optional[bool] = typer.Option(
        None, help="Save outputs in execution directory"
    ),
) -> None:
    """Update global settings."""
    from codewrap.settings import SettingsManager

    mgr = SettingsManager()
    settings = mgr.load()
    if encoding is not None:
        settings.encoding = encoding
    if exclude_binary is not None:
        settings.exclude_binary = exclude_binary
    if numbered is not None:
        settings.use_numbering = numbered
    if cwd is not None:
        settings.save_in_cwd = cwd

    mgr.save(settings)
    console.print("[bold green]✅ Global settings updated![/bold green]")


@config_app.command("reset")
def config_reset() -> None:
    """Reset all stored global settings to default."""
    from codewrap.settings import SettingsManager

    mgr = SettingsManager()
    mgr.reset()
    console.print(
        "[bold green]🧹 Global settings successfully reset to defaults![/bold green]"
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    directory: Optional[Path] = typer.Argument(
        None, help="Project root path (defaults to current folder or preset root)"
    ),
    target: Optional[List[str]] = typer.Option(
        None,
        "--target",
        "-t",
        help="Scan target rule e.g. 'folder:py,toml' or 'path/file.py'",
    ),
    files_list: Optional[Path] = typer.Option(
        None,
        "--files-list",
        "-f",
        help="Path to text file containing file paths to process",
    ),
    modified: bool = typer.Option(
        False, "--modified", "-m", help="Gather only Git modified/uncommitted files"
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        "-s",
        help="Gather Git files modified since date/commit (e.g. '3 days ago')",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        "-d",
        help="Generate a Git unified diff context instead of full files",
    ),
    patch: bool = typer.Option(
        False,
        "--patch",
        "-pt",
        help="Smart diff mode: Git diff for modified files, full content for new files",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Custom output Markdown file path"
    ),
    preset: Optional[str] = typer.Option(
        None, "--preset", "-p", help="Load named preset configuration"
    ),
    save_preset: Optional[str] = typer.Option(
        None, "--save-preset", "-sp", help="Save current options as a named preset"
    ),
    bind: bool = typer.Option(
        False,
        "--bind",
        "-b",
        help="Bind the saved/loaded preset to current directory (Zero-Clutter)",
    ),
    init_config: bool = typer.Option(
        False,
        "--init-config",
        "-ic",
        help="Create a local .codewrap.json config file in current directory",
    ),
    presets_dir: Optional[Path] = typer.Option(
        None, "--presets-dir", "-pd", help="Custom presets directory path"
    ),
    list_presets: bool = typer.Option(
        False, "--list-presets", "-lp", help="List all available presets"
    ),
    numbered: Optional[bool] = typer.Option(
        None, "--numbered", "-n", help="Enable file numbering for duplicates (_1.md)"
    ),
    save_in_cwd: Optional[bool] = typer.Option(
        None,
        "--cwd",
        "-w",
        help="Save output Markdown in current terminal execution folder",
    ),
    copy: Optional[bool] = typer.Option(
        None, "--copy", "-c", help="Copy generated Markdown to clipboard"
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    from codewrap.engine import CodeProcessorEngine
    from codewrap.git import GitHelper
    from codewrap.models import PresetConfig, TargetRule
    from codewrap.presets import PresetManager
    from codewrap.settings import SettingsManager

    settings_mgr = SettingsManager()
    saved_settings = settings_mgr.load()

    if presets_dir is not None:
        saved_settings.presets_dir = str(presets_dir.resolve())
    if numbered is not None:
        saved_settings.use_numbering = numbered
    if copy is not None:
        saved_settings.copy_to_clipboard = copy
    if save_in_cwd is not None:
        saved_settings.save_in_cwd = save_in_cwd

    settings_mgr.save(saved_settings)

    effective_presets_dir = (
        Path(saved_settings.presets_dir) if saved_settings.presets_dir else None
    )
    preset_mgr = PresetManager(custom_dir=effective_presets_dir)

    if list_presets:
        presets = preset_mgr.list_presets()
        if not presets:
            console.print(
                f"[yellow]No presets found in: {preset_mgr.presets_dir}[/yellow]"
            )
        else:
            console.print(
                f"[bold blue]Available Presets ({preset_mgr.presets_dir}):[/bold blue]"
            )
            for p in presets:
                console.print(f"  • {p}")
        return

    current_folder = (directory or Path(".")).resolve()

    # Validate target directory existence
    if not current_folder.exists() or not current_folder.is_dir():
        console.print(
            f"[bold red]❌ Error: Path '{current_folder}' does not exist or is not a directory.[/bold red]"
        )
        raise typer.Exit(1)

    # Handle Git Diff Mode (-d / --diff)
    if diff:
        if not GitHelper.is_git_repo(current_folder):
            console.print("[red]❌ Not a Git repository! Cannot generate diff.[/red]")
            raise typer.Exit(1)
        diff_text = GitHelper.get_diff_text(current_folder, ref=since)
        if not diff_text.strip():
            console.print("[yellow]⚠️ No Git diff changes found.[/yellow]")
            raise typer.Exit(0)

        dummy_config = PresetConfig(
            root_path=str(current_folder), output_file=str(output) if output else None
        )
        engine = CodeProcessorEngine(
            dummy_config, exclude_binary=saved_settings.exclude_binary
        )
        files, tokens = engine.process_diff(diff_text)
        console.print(
            f"\n[bold green]✅ Git Diff Generated![/bold green] Tokens (≈): [cyan]{tokens}[/cyan]"
        )
        console.print(
            f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]"
        )
        if saved_settings.copy_to_clipboard or copy:
            try:
                import pyperclip

                pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
                console.print("[bold green]📋 Diff copied to clipboard![/bold green]")
            except Exception as e:
                console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")
        return

    # Handle Smart Patch Mode (-pt / --patch)
    if patch:
        if not GitHelper.is_git_repo(current_folder):
            console.print("[red]❌ Not a Git repository! Cannot generate patch.[/red]")
            raise typer.Exit(1)

        status_files = GitHelper.get_status_files(current_folder)
        if not status_files:
            console.print(
                "[yellow]⚠️ No uncommitted changes or new files found.[/yellow]"
            )
            raise typer.Exit(0)

        dummy_config = PresetConfig(
            root_path=str(current_folder), output_file=str(output) if output else None
        )
        engine = CodeProcessorEngine(
            dummy_config, exclude_binary=saved_settings.exclude_binary
        )

        def cli_progress(path: Path, tokens: int, total_tokens: int):
            console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")

        console.print(
            f"[bold blue]🛠 Generating Smart Patch for:[/bold blue] {current_folder}"
        )
        files, tokens = engine.process_patch(
            status_files, progress_callback=cli_progress
        )

        console.print(
            f"\n[bold green]✅ Smart Patch Generated![/bold green] Items: {files} | Tokens (≈): [cyan]{tokens}[/cyan]"
        )
        console.print(
            f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]"
        )

        if saved_settings.copy_to_clipboard or copy:
            try:
                import pyperclip

                pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
                console.print("[bold green]📋 Patch copied to clipboard![/bold green]")
            except Exception as e:
                console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")
        return

    target_preset = preset

    # Zero-Clutter folder binding lookup
    if (
        not target_preset
        and not target
        and not files_list
        and not modified
        and not since
    ):
        bound_preset = settings_mgr.get_bound_preset(current_folder)
        if bound_preset:
            target_preset = bound_preset
            console.print(
                f"[dim]🔗 Auto-detected bound preset for folder: {bound_preset}[/dim]"
            )

    config: Optional[PresetConfig] = None

    if target_preset:
        config = preset_mgr.load_preset(target_preset)
        if not config:
            console.print(
                f"[red]❌ Preset '{target_preset}' not found in {preset_mgr.presets_dir}![/red]"
            )
            raise typer.Exit(1)
        console.print(f"[green]Loaded preset:[/green] {target_preset}")

        if directory is not None:
            config.root_path = str(directory.resolve())
        if output is not None:
            config.output_file = str(output)
    else:
        local_config = preset_mgr.load_local_config(current_folder)
        if (
            local_config
            and not target
            and not files_list
            and not modified
            and not since
        ):
            config = local_config
            console.print("[dim]📄 Auto-loaded local config (.codewrap.json)[/dim]")
        else:
            rules: List[TargetRule] = []

            if modified:
                if not GitHelper.is_git_repo(current_folder):
                    console.print("[red]❌ Not a Git repository![/red]")
                    raise typer.Exit(1)
                git_files = GitHelper.get_modified_files(current_folder)
                console.print(
                    f"[dim]🌿 Git modified files detected: {len(git_files)}[/dim]"
                )
                rules = [TargetRule(path=str(f)) for f in git_files]
            elif since:
                if not GitHelper.is_git_repo(current_folder):
                    console.print("[red]❌ Not a Git repository![/red]")
                    raise typer.Exit(1)
                git_files = GitHelper.get_files_since(current_folder, since)
                console.print(
                    f"[dim]🌿 Git files changed since '{since}': {len(git_files)}[/dim]"
                )
                rules = [TargetRule(path=str(f)) for f in git_files]
            elif target:
                rules = [parse_target_arg(t) for t in target]
            elif files_list:
                fl_path = (
                    files_list
                    if files_list.is_absolute()
                    else current_folder / files_list
                )
                if fl_path.exists():
                    for line in fl_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            rules.append(parse_target_arg(line))
            elif GitHelper.is_git_repo(current_folder):
                tracked_files = GitHelper.get_tracked_files(current_folder)
                console.print(
                    f"[dim]🌿 Git repository auto-detected ({len(tracked_files)} tracked files)[/dim]"
                )
                rules = [TargetRule(path=str(f)) for f in tracked_files]

            root = infer_common_root(rules, current_folder)

            config = PresetConfig(
                root_path=str(root),
                targets=rules,
                output_file=str(output) if output else None,
                copy_to_clipboard=saved_settings.copy_to_clipboard,
                use_numbering=saved_settings.use_numbering,
                save_in_cwd=saved_settings.save_in_cwd,
                encoding=saved_settings.encoding,
            )

    if save_preset:
        config.name = save_preset
        saved_path = preset_mgr.save_preset(config, save_preset)
        console.print(
            f"[bold green]Saved preset:[/bold green] {save_preset} ({saved_path})"
        )
        if bind:
            settings_mgr.bind_folder(current_folder, save_preset)
            console.print(
                f"[bold cyan]🔗 Bound folder '{current_folder}' to preset '{save_preset}'[/bold cyan]"
            )

    if init_config:
        local_file = preset_mgr.init_local_config(current_folder, config)
        console.print(
            f"[bold green]Created local config file:[/bold green] {local_file}"
        )

    engine = CodeProcessorEngine(config, exclude_binary=saved_settings.exclude_binary)

    def cli_progress(path: Path, tokens: int, total_tokens: int):
        console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")

    console.print(f"[bold blue]🛠 Gathering context for:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=cli_progress)

    console.print(
        f"\n[bold green]✅ Done![/bold green] Files: {files} | Tokens (≈): [cyan]{tokens}[/cyan]"
    )
    console.print(
        f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]"
    )

    if config.copy_to_clipboard:
        try:
            import pyperclip

            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print(
                "[bold green]📋 Content successfully copied to clipboard![/bold green]"
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")
