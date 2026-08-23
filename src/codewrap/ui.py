"""Shared Rich console feedback helpers used across CLI entry points."""

from pathlib import Path

from rich.console import Console

console = Console()


def print_progress(path: Path, tokens: int, total_tokens: int) -> None:
    """Print a single processed-file progress line."""
    console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")


def print_skipped_summary(skipped_files: list[Path]) -> None:
    """Print a summary of files skipped during processing."""
    if not skipped_files:
        return
    console.print(f"[yellow]⚠️ Skipped {len(skipped_files)} file(s):[/yellow]")
    for skipped in skipped_files:
        console.print(f"  • {skipped}")


def copy_output_to_clipboard(output_file: Path, label: str = "Content") -> None:
    """Copy the generated Markdown output to the clipboard with friendly reporting."""
    try:
        import pyperclip

        pyperclip.copy(output_file.read_text(encoding="utf-8"))
        console.print(f"[bold green]📋 {label} successfully copied to clipboard![/bold green]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")
