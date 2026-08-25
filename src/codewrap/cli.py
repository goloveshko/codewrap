import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from codewrap.cli_group import GlobalOptionsGroup
from codewrap.handlers import resolve_scan_config, run_diff_mode, run_patch_mode
from codewrap.presets import PresetManager
from codewrap.settings import SettingsManager
from codewrap.ui import console, copy_output_to_clipboard, print_progress, print_skipped_summary

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    cls=GlobalOptionsGroup,
    help="CodeWrap: Professional LLM context gatherer for source code bases.",
    add_completion=False,
    context_settings=CONTEXT_SETTINGS,
)
config_app = typer.Typer(
    help="Manage global CodeWrap settings. Runs 'show' by default if no subcommand is passed.",
    context_settings=CONTEXT_SETTINGS,
)
app.add_typer(config_app, name="config")

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, show_time=False, show_path=False)],
)


def _render_config_table() -> None:
    """Renders global settings as an informative Rich Table."""
    mgr = SettingsManager()
    settings = mgr.load()

    table = Table(
        title="⚙️  CodeWrap Global Configuration",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Setting Key", style="bold yellow", no_wrap=True)
    table.add_column("Current Value", style="green")
    table.add_column("Type / Choices", style="magenta")
    table.add_column("Description", style="white")

    table.add_row(
        "encoding",
        str(settings.encoding),
        "string (e.g. o200k_base, cl100k_base)",
        "Tokenizer encoding for calculating LLM tokens",
    )
    table.add_row(
        "exclude_binary",
        str(settings.exclude_binary),
        "true | false",
        "Auto-exclude binary files and media assets (.png, .exe, etc.)",
    )
    table.add_row(
        "use_numbering",
        str(settings.use_numbering),
        "true | false",
        "Prevent overwriting existing output by appending suffix (_1.md, _2.md)",
    )
    table.add_row(
        "copy_to_clipboard",
        str(settings.copy_to_clipboard),
        "true | false",
        "Automatically copy generated context directly to clipboard",
    )
    table.add_row(
        "save_in_cwd",
        str(settings.save_in_cwd),
        "true | false",
        "Save context files in execution directory instead of project root",
    )
    table.add_row(
        "presets_dir",
        str(settings.presets_dir or "~/.codewrap/presets (default)"),
        "path | null",
        "Custom directory where reusable preset configs are stored",
    )

    bindings_str = (
        "\n".join([f"{k} ➔ {v}" for k, v in settings.folder_bindings.items()]) if settings.folder_bindings else "none"
    )
    table.add_row(
        "folder_bindings",
        bindings_str,
        "dict (auto-managed)",
        "Zero-Clutter directory-to-preset automatic bindings",
    )

    console.print(table)
    console.print(
        Panel(
            "[dim]💡 Tip: Use [bold cyan]codewrap config set --key value[/bold cyan] to update settings or "
            "[bold cyan]codewrap config reset[/bold cyan] to restore defaults.[/dim]",
            border_style="dim",
        )
    )


@config_app.callback(invoke_without_command=True)
def config_main(ctx: typer.Context) -> None:
    """Manage global CodeWrap settings."""
    if ctx.invoked_subcommand is None:
        _render_config_table()


@config_app.command("show")
def config_show(
    raw_json: bool = typer.Option(False, "--json", "-j", help="Print raw JSON format for scripting"),
) -> None:
    """Show current global settings."""
    if raw_json:
        mgr = SettingsManager()
        console.print(mgr.load().model_dump_json(indent=2))
    else:
        _render_config_table()


def _is_known_encoding(name: str) -> bool:
    """Check that tiktoken recognizes the encoding name."""
    try:
        import tiktoken

        tiktoken.get_encoding(name)
    except Exception:
        return False
    return True


@config_app.command("set")
def config_set(
    encoding: str | None = typer.Option(None, help="Default tokenizer encoding (e.g. o200k_base, cl100k_base)"),
    exclude_binary: bool | None = typer.Option(None, help="Auto-exclude binary and media asset files"),
    numbered: bool | None = typer.Option(
        None, help="Auto-number duplicate output files (_1.md, _2.md) instead of overwriting"
    ),
    copy: bool | None = typer.Option(None, help="Auto-copy generated context to clipboard by default"),
    cwd: bool | None = typer.Option(None, help="Save outputs in current execution directory by default"),
    presets_dir: Path | None = typer.Option(None, help="Custom folder path to store presets"),
) -> None:
    """Update global settings."""
    mgr = SettingsManager()
    settings = mgr.load()

    if encoding is not None:
        if not _is_known_encoding(encoding):
            console.print(f"[bold red]❌ Unknown tokenizer encoding '{encoding}'.[/bold red]")
            raise typer.Exit(1)
        settings.encoding = encoding
    if exclude_binary is not None:
        settings.exclude_binary = exclude_binary
    if numbered is not None:
        settings.use_numbering = numbered
    if copy is not None:
        settings.copy_to_clipboard = copy
    if cwd is not None:
        settings.save_in_cwd = cwd
    if presets_dir is not None:
        settings.presets_dir = str(presets_dir.resolve())

    mgr.save(settings)
    console.print("[bold green]✅ Global settings updated![/bold green]")


@config_app.command("reset")
def config_reset() -> None:
    """Reset all stored global settings to default."""
    SettingsManager().reset()
    console.print("[bold green]🧹 Global settings successfully reset to defaults![/bold green]")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    directory: Path | None = typer.Argument(None, help="Project root path (defaults to current folder or preset root)"),
    target: list[str] | None = typer.Option(
        None,
        "--target",
        "-t",
        help="Scan target rule e.g. 'folder:py,toml' or 'path/file.py'",
    ),
    files_list: Path | None = typer.Option(
        None,
        "--files-list",
        "-f",
        help="Path to text file containing file paths to process",
    ),
    modified: bool = typer.Option(False, "--modified", "-m", help="Gather only Git modified/uncommitted files"),
    since: str | None = typer.Option(
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
    output: Path | None = typer.Option(None, "--output", "-o", help="Custom output Markdown file path"),
    preset: str | None = typer.Option(None, "--preset", "-p", help="Load named preset configuration"),
    save_preset: str | None = typer.Option(None, "--save-preset", "-sp", help="Save current options as a named preset"),
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
    presets_dir: Path | None = typer.Option(None, "--presets-dir", "-pd", help="Custom presets directory path"),
    list_presets: bool = typer.Option(False, "--list-presets", "-lp", help="List all available presets"),
    numbered: bool | None = typer.Option(
        None,
        "--numbered",
        "-n",
        help="Enable auto-numbering for duplicate files (_1.md) instead of overwriting",
    ),
    save_in_cwd: bool | None = typer.Option(
        None,
        "--cwd",
        "-w",
        help="Save output Markdown in current terminal execution folder",
    ),
    copy: bool | None = typer.Option(None, "--copy", "-c", help="Copy generated Markdown to clipboard"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    from codewrap.engine import CodeProcessorEngine

    settings_mgr = SettingsManager()
    saved_settings = settings_mgr.load()
    session_settings = saved_settings.model_copy()

    if presets_dir is not None:
        session_settings.presets_dir = str(presets_dir.resolve())
    if numbered is not None:
        session_settings.use_numbering = numbered
    if copy is not None:
        session_settings.copy_to_clipboard = copy
    if save_in_cwd is not None:
        session_settings.save_in_cwd = save_in_cwd

    effective_presets_dir = Path(session_settings.presets_dir) if session_settings.presets_dir else None
    preset_mgr = PresetManager(custom_dir=effective_presets_dir)

    if list_presets:
        presets = preset_mgr.list_presets()
        if not presets:
            console.print(f"[yellow]No presets found in: {preset_mgr.presets_dir}[/yellow]")
        else:
            console.print(f"[bold blue]Available Presets ({preset_mgr.presets_dir}):[/bold blue]")
            for p in presets:
                console.print(f"  • {p}")
        return

    current_folder = (directory or Path(".")).resolve()

    if not current_folder.exists() or not current_folder.is_dir():
        console.print(f"[bold red]❌ Error: Path '{current_folder}' does not exist or is not a directory.[/bold red]")
        raise typer.Exit(1)

    if diff:
        run_diff_mode(current_folder, since, output, session_settings)
        return

    if patch:
        run_patch_mode(current_folder, output, session_settings)
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
        session_settings,
        directory is not None,
    )

    if save_preset:
        config.name = save_preset
        saved_path = preset_mgr.save_preset(config, save_preset)
        console.print(f"[bold green]Saved preset:[/bold green] {save_preset} ({saved_path})")
        if bind:
            settings_mgr.bind_folder(current_folder, save_preset)
            console.print(f"[bold cyan]🔗 Bound folder '{current_folder}' to preset '{save_preset}'[/bold cyan]")

    if init_config:
        local_file = preset_mgr.init_local_config(current_folder, config)
        console.print(f"[bold green]Created local config file:[/bold green] {local_file}")

    engine = CodeProcessorEngine(config, exclude_binary=session_settings.exclude_binary)

    console.print(f"[bold blue]🛠 Gathering context for:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=print_progress)

    console.print(f"\n[bold green]✅ Done![/bold green] Files: {files} | Tokens (≈): [cyan]{tokens}[/cyan]")
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    print_skipped_summary(engine.skipped_files)

    if config.copy_to_clipboard or copy:
        copy_output_to_clipboard(engine.output_file, label="Content")
