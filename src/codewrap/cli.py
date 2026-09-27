import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from codewrap.cli_group import GlobalOptionsGroup
from codewrap.handlers import (
    create_engine,
    resolve_scan_config,
    run_diff_since_mode,
    run_smart_diff_mode,
)
from codewrap.settings import SettingsManager
from codewrap.tokenizers import MODEL_ALIASES, resolve_tokenizer
from codewrap.ui import (
    console,
    copy_output_to_clipboard,
    print_progress,
    print_skipped_summary,
    print_token_summary,
)
from codewrap.utils import parse_size_arg, parse_split_arg

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
        "-e, --encoding",
        "Token counting encoding or model alias (run 'codewrap config tokenizers' for the guide)",
    )
    core_table.add_row(
        "exclude_binary",
        str(settings.exclude_binary),
        "--exclude-binary / --no-exclude-binary",
        "Auto-exclude binary files and media assets (.png, .exe, content sniffing)",
    )
    core_table.add_row(
        "max_file_size",
        str(settings.max_file_size),
        "-M, --max-file-size",
        "Skip files larger than this size (e.g. '512kb', '2mb'); 0 disables the limit",
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
    """List supported tokenizers, model aliases, and what they approximate."""
    table = Table(
        title="🧠 Token counting (tiktoken)",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Encoding", style="bold yellow", no_wrap=True)
    table.add_column("Model Aliases", style="green")
    table.add_column("Notes", style="white")

    table.add_row(
        "o200k_base (default)",
        ", ".join(k for k, v in MODEL_ALIASES.items() if v == "o200k_base"),
        "OpenAI 200k vocabulary — accurate for GPT-4o/o1/o3-class models.",
    )
    table.add_row(
        "cl100k_base",
        ", ".join(k for k, v in MODEL_ALIASES.items() if v == "cl100k_base"),
        "OpenAI 100k vocabulary — the standard approximation used for Claude and older GPT models.",
    )

    console.print(table)
    console.print(
        Panel(
            "[dim]💡 Any tiktoken encoding name is also accepted. Pick by target model: "
            "[bold cyan]codewrap -e claude[/bold cyan] or [bold cyan]codewrap config set --tokenizer claude[/bold cyan].[/dim]",
            border_style="dim",
        )
    )


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
        None,
        "--tokenizer",
        "-t",
        help="Default tokenizer for counting: encoding name or model alias (run 'codewrap config tokenizers')",
    ),
    exclude_binary: bool | None = typer.Option(None, help="Auto-exclude binary and media asset files"),
    rename: bool | None = typer.Option(
        None, "--rename", "-r", help="Auto-rename duplicate files (_1.md, _2.md) instead of overwriting"
    ),
    copy: bool | None = typer.Option(None, "--copy", "-c", help="Auto-copy generated context to clipboard by default"),
    cwd: bool | None = typer.Option(None, "--cwd", "-w", help="Save outputs in current execution directory by default"),
    max_file_size: str | None = typer.Option(
        None, "--max-file-size", help="Default size cap for included files, e.g. '512kb' (0 disables)"
    ),
) -> None:
    """Update global settings."""
    mgr = SettingsManager()
    settings = mgr.load()

    if tokenizer is not None:
        resolved = resolve_tokenizer(tokenizer)
        if not _is_known_tokenizer(resolved):
            console.print(f"[bold red]❌ Unknown tokenizer '{tokenizer}'.[/bold red]")
            raise typer.Exit(1)
        settings.tokenizer = resolved
    if exclude_binary is not None:
        settings.exclude_binary = exclude_binary
    if rename is not None:
        settings.auto_rename_outputs = rename
    if copy is not None:
        settings.copy_to_clipboard = copy
    if cwd is not None:
        settings.save_in_current_dir = cwd
    if max_file_size is not None:
        try:
            parse_size_arg(max_file_size)
        except ValueError as e:
            console.print(f"[bold red]❌ {e}[/bold red]")
            raise typer.Exit(1) from None
        settings.max_file_size = max_file_size

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
    encoding: str | None = typer.Option(
        None,
        "--encoding",
        "-e",
        help="Count tokens for a target model: 'claude', 'gpt-4o', or a tiktoken encoding name",
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
    max_file_size: str | None = typer.Option(
        None,
        "--max-file-size",
        "-M",
        help="Skip files larger than this size, e.g. '512kb', '2mb' (bare number = bytes; 0 disables the limit)",
    ),
    split: str | None = typer.Option(
        None,
        "--split",
        "-S",
        help="Split large output into a folder of budgeted parts + manifest. Bare number = tokens (e.g. '50000'); "
        "with a suffix = bytes (e.g. '256kb')",
    ),
    per_file: bool = typer.Option(
        False,
        "--per-file",
        "-p",
        help="Copy each collected file separately into the output folder as 'NNN_path_file.ext.txt' "
        "instead of building one document",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

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
    if encoding is not None:
        resolved = resolve_tokenizer(encoding)
        if not _is_known_tokenizer(resolved):
            raise _fail(f"Unknown tokenizer or model '{encoding}'. See 'codewrap config tokenizers'.")
        session_settings.tokenizer = resolved
    if max_file_size is not None:
        try:
            parse_size_arg(max_file_size)
        except ValueError as e:
            raise _fail(str(e)) from None
        session_settings.max_file_size = max_file_size

    if split is not None:
        try:
            parse_split_arg(split)
        except ValueError as e:
            raise _fail(str(e)) from None

    if per_file:
        if diff:
            raise _fail("--per-file copies whole files; it does not combine with --diff.")
        if split is not None:
            raise _fail("--per-file already produces one file per source; drop --split.")

    if diff:
        if since:
            if split is not None:
                raise _fail(
                    "--split does not apply to a raw --since diff; drop --diff to bundle changed files instead."
                )
            run_diff_since_mode(current_folder, since, output, None, session_settings)
        else:
            run_smart_diff_mode(current_folder, output, None, session_settings, split=split)
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
        split=split,
        per_file=per_file,
    )

    engine = create_engine(config, session_settings)

    console.print(f"[bold blue]🛠 Gathering context for:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=print_progress)

    print_token_summary(f"✅ Done! Files: {files} |", tokens, engine.encoding_name, engine.estimate_reason)
    if engine.bundle_folder is not None:
        label = "📂 Files copied to:" if per_file else "📂 Result split into parts under:"
        console.print(f"{label} [bold underline]{engine.bundle_folder}[/bold underline]")
    else:
        console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    print_skipped_summary(engine.excluded)

    if config.copy_to_clipboard or copy:
        if engine.bundle_folder is not None:
            console.print("[yellow]⚠️ Clipboard skipped: output was split into parts — copy them one by one.[/yellow]")
        else:
            copy_output_to_clipboard(engine.output_file, label="Content")
