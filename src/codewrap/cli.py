import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from codewrap.cli_group import GlobalOptionsGroup
from codewrap.handlers import (
    resolve_scan_config,
    run_diff_since_mode,
    run_smart_diff_mode,
)
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
    """Render global settings as a Rich table."""
    settings = SettingsManager().load()

    core_table = Table(
        title="⚙️  CodeWrap Global Configuration",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    core_table.add_column("Setting Key", style="bold yellow", no_wrap=True)
    core_table.add_column("Current Value", style="green")
    core_table.add_column("CLI Override Flag", style="magenta")
    core_table.add_column("Description", style="white")

    core_table.add_row(
        "tokenizer",
        str(settings.tokenizer),
        "--tokenizer",
        "LLM Tokenizer (run 'codewrap config tokenizers' for model guide)",
    )
    core_table.add_row(
        "exclude_binary",
        str(settings.exclude_binary),
        "--exclude-binary / --no-exclude-binary",
        "Auto-exclude binary files and media assets (.png, .exe, null bytes)",
    )
    core_table.add_row(
        "auto_rename_outputs",
        str(settings.auto_rename_outputs),
        "-r, --rename",
        "Auto-rename duplicate output files (_1.md, _2.md) instead of overwriting",
    )
    core_table.add_row(
        "copy_to_clipboard",
        str(settings.copy_to_clipboard),
        "-c, --copy",
        "Automatically copy generated markdown context directly to clipboard",
    )
    core_table.add_row(
        "save_in_current_dir",
        str(settings.save_in_current_dir),
        "-w, --cwd",
        "Save context file in current terminal directory instead of project root",
    )

    console.print(core_table)
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


@config_app.command("tokenizers")
def config_tokenizers() -> None:
    """List supported tokenizers and their corresponding LLM models."""
    table = Table(
        title="🧠 Supported LLM Tokenizers (tiktoken)",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Tokenizer Name", style="bold yellow", no_wrap=True)
    table.add_column("Target Models", style="green")
    table.add_column("Vocabulary / Description", style="white")

    table.add_row(
        "o200k_base (default)",
        "GPT-4o, GPT-4o mini, o1, o3-mini",
        "OpenAI 200k vocabulary. Most accurate for modern models and codebases.",
    )
    table.add_row(
        "cl100k_base",
        "GPT-4, GPT-4 Turbo, GPT-3.5-Turbo, Claude",
        "OpenAI 100k vocabulary. General-purpose standard for 2023-2024 models.",
    )

    console.print(table)


def _is_known_tokenizer(name: str) -> bool:
    """Check that tiktoken recognizes the tokenizer name."""
    try:
        import tiktoken

        tiktoken.get_encoding(name)
    except Exception:
        return False
    return True


@config_app.command("set")
def config_set(
    tokenizer: str | None = typer.Option(
        None, "--tokenizer", "-t", help="Default tokenizer (e.g. o200k_base, cl100k_base)"
    ),
    exclude_binary: bool | None = typer.Option(None, help="Auto-exclude binary and media asset files"),
    rename: bool | None = typer.Option(
        None, "--rename", "-r", help="Auto-rename duplicate files (_1.md, _2.md) instead of overwriting"
    ),
    copy: bool | None = typer.Option(None, "--copy", "-c", help="Auto-copy generated context to clipboard by default"),
    cwd: bool | None = typer.Option(None, "--cwd", "-w", help="Save outputs in current execution directory by default"),
) -> None:
    """Update global settings."""
    mgr = SettingsManager()
    settings = mgr.load()

    if tokenizer is not None:
        if not _is_known_tokenizer(tokenizer):
            console.print(f"[bold red]❌ Unknown tokenizer '{tokenizer}'.[/bold red]")
            raise typer.Exit(1)
        settings.tokenizer = tokenizer
    if exclude_binary is not None:
        settings.exclude_binary = exclude_binary
    if rename is not None:
        settings.auto_rename_outputs = rename
    if copy is not None:
        settings.copy_to_clipboard = copy
    if cwd is not None:
        settings.save_in_current_dir = cwd

    mgr.save(settings)
    console.print("[bold green]✅ Global settings updated![/bold green]")


@config_app.command("reset")
def config_reset() -> None:
    """Reset all stored global settings to default."""
    SettingsManager().reset()
    console.print("[bold green]🧹 Global settings successfully reset to defaults![/bold green]")


def _fail(message: str) -> typer.Exit:
    """Print a CLI usage error and build the exit exception (raise at call site)."""
    console.print(f"[red]❌ {message}[/red]")
    return typer.Exit(2)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    paths: list[str] = typer.Argument(
        None,
        help="One PATH = project root to scan. Multiple values = explicit file/folder targets "
        "or 'folder:ext' rules (relative to the current directory).",
    ),
    files_list: Path | None = typer.Option(
        None,
        "--files-list",
        "-f",
        help="Path to text file containing file paths to process",
    ),
    modified: bool = typer.Option(
        False, "--modified", "-m", help="Gather only Git modified and new (uncommitted) files"
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        "-s",
        help="Since date (e.g. '3 days ago'). Standalone: full files changed since date. With --diff: diff vs that date",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        "-d",
        help="Diff mode: unified diff for modified files, full content for new files (combine with --since for a date range)",
    ),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Exclude glob pattern, e.g. -x 'tests/**' -x '*.lock' (repeatable)",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Custom output Markdown file path"),
    rename: bool | None = typer.Option(
        None,
        "--rename",
        "-r",
        help="Auto-rename duplicate files (_1.md) instead of overwriting existing output",
    ),
    save_in_current_dir: bool | None = typer.Option(
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

    args = list(paths or [])
    if len(args) == 1 and Path(args[0]).is_dir():
        # A single existing directory is the project root; anything else is a scan target.
        current_folder = Path(args[0]).resolve()
        targets: list[str] = []
    else:
        current_folder = Path(".").resolve()
        targets = args

    # Validate flag combinations: each selects a different file source, so they must not overlap.
    if diff:
        if modified or files_list or targets:
            raise _fail("--diff works on Git changes only; drop --modified/--files-list/target arguments.")
        if exclude:
            raise _fail("--diff writes a raw Git diff; --exclude does not apply to it.")
    else:
        sources = [bool(targets), files_list is not None, modified, since is not None]
        if sum(sources) > 1:
            raise _fail("Choose only one source: target arguments, --files-list, --modified, or --since.")

    if not current_folder.exists() or not current_folder.is_dir():
        raise _fail(f"Path '{current_folder}' does not exist or is not a directory.")

    settings_mgr = SettingsManager()
    session_settings = settings_mgr.load().model_copy()

    if rename is not None:
        session_settings.auto_rename_outputs = rename
    if copy is not None:
        session_settings.copy_to_clipboard = copy
    if save_in_current_dir is not None:
        session_settings.save_in_current_dir = save_in_current_dir

    if diff:
        if since:
            run_diff_since_mode(current_folder, since, output, None, session_settings)
        else:
            run_smart_diff_mode(current_folder, output, None, session_settings)
        return

    config = resolve_scan_config(
        current_folder,
        targets,
        files_list,
        modified,
        since,
        exclude or [],
        output,
        session_settings,
    )

    engine = CodeProcessorEngine(config, exclude_binary=session_settings.exclude_binary)

    console.print(f"[bold blue]🛠 Gathering context for:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=print_progress)

    console.print(f"\n[bold green]✅ Done![/bold green] Files: {files} | Tokens (≈): [cyan]{tokens}[/cyan]")
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    print_skipped_summary(engine.skipped_files)

    if config.copy_to_clipboard or copy:
        copy_output_to_clipboard(engine.output_file, label="Content")
