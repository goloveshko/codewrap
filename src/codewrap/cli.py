from pathlib import Path
from typing import List, Optional
from rich.console import Console
import typer

from codewrap.handlers import resolve_scan_config, run_diff_mode, run_patch_mode
from codewrap.presets import PresetManager
from codewrap.settings import SettingsManager

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


@config_app.command("show")
def config_show() -> None:
    """Show current global settings."""
    mgr = SettingsManager()
    console.print("[bold blue]Current Global Settings:[/bold blue]")
    console.print(mgr.load().model_dump_json(indent=2))


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
    SettingsManager().reset()
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

    if not current_folder.exists() or not current_folder.is_dir():
        console.print(
            f"[bold red]❌ Error: Path '{current_folder}' does not exist or is not a directory.[/bold red]"
        )
        raise typer.Exit(1)

    if diff:
        run_diff_mode(current_folder, since, output, bool(copy), saved_settings)
        return

    if patch:
        run_patch_mode(current_folder, output, bool(copy), saved_settings)
        return

    config = resolve_scan_config(
        current_folder,
        preset,
        target,
        files_list,
        modified,
        since,
        output,
        preset_mgr,
        saved_settings,
        directory is not None,
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

    if config.copy_to_clipboard or copy:
        try:
            import pyperclip

            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print(
                "[bold green]📋 Content successfully copied to clipboard![/bold green]"
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")
