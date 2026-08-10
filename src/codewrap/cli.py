from pathlib import Path
from typing import List, Optional
from rich.console import Console
import typer

from codewrap.engine import CodeProcessorEngine
from codewrap.models import PresetConfig, TargetRule
from codewrap.presets import PresetManager
from codewrap.settings import SettingsManager

app = typer.Typer(
    help="CodeWrap: Professional LLM context gatherer for source code bases.",
    add_completion=False,
)
console = Console()


def parse_target_arg(target_str: str) -> TargetRule:
    target_str = target_str.strip()
    last_colon = target_str.rfind(":")
    if last_colon > 1:
        exts_part = target_str[last_colon + 1:].strip()
        if "/" not in exts_part and "\\" not in exts_part:
            path_part = target_str[:last_colon].strip()
            exts = [e.strip() for e in exts_part.split(",") if e.strip()]
            return TargetRule(path=path_part, extensions=exts)
    return TargetRule(path=target_str)


def infer_common_root(rules: List[TargetRule], default_root: Path) -> Path:
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


@app.command()
def main(
    directory: Optional[Path] = typer.Argument(
        None, help="Project root path (defaults to current folder or preset root)"
    ),
    target: Optional[List[str]] = typer.Option(
        None, "--target", "-t", help="Scan target rule e.g. 'folder:py,toml' or 'path/file.py'"
    ),
    files_list: Optional[Path] = typer.Option(
        None, "--files-list", "-f", help="Path to text file containing file paths to process (one per line)"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Custom output Markdown file path"),
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Load named preset configuration"),
    save_preset: Optional[str] = typer.Option(
        None, "--save-preset", "-sp", "-s", help="Save current execution options as a named preset"
    ),
    bind: bool = typer.Option(
        False, "--bind", "-b", help="Bind the saved/loaded preset to the current directory (Zero-Clutter)"
    ),
    init_config: bool = typer.Option(
        False, "--init-config", help="Create a local .codewrap.json config file in the current directory"
    ),
    last: bool = typer.Option(False, "--last", "-l", help="Re-run the last executed preset"),
    presets_dir: Optional[Path] = typer.Option(None, "--presets-dir", "-pd", help="Custom presets directory path"),
    list_presets: bool = typer.Option(False, "--list-presets", "-lp", help="List all available presets"),
    numbered: Optional[bool] = typer.Option(None, "--numbered", "-n", help="Enable file numbering for duplicates (_1.md)"),
    save_in_cwd: Optional[bool] = typer.Option(
        None, "--cwd", "-w", help="Save output Markdown in current terminal execution folder"
    ),
    copy: Optional[bool] = typer.Option(None, "--copy", "-c", help="Copy generated Markdown to clipboard"),
    clear_settings: bool = typer.Option(
        False, "--clear-settings", "-cs", "--reset-config", help="Reset all stored global application settings"
    ),
) -> None:
    settings_mgr = SettingsManager()

    if clear_settings:
        settings_mgr.reset()
        console.print("[bold green]🧹 Global settings successfully reset![/bold green]")
        return

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

    effective_presets_dir = Path(saved_settings.presets_dir) if saved_settings.presets_dir else None
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

    # Determine preset to execute (Explicit -> Bound -> Local Config -> Auto)
    target_preset = preset
    if last:
        if not saved_settings.last_preset:
            console.print("[red]❌ No saved last preset found![/red]")
            raise typer.Exit(1)
        target_preset = saved_settings.last_preset

    # Check Zero-Clutter folder binding if no explicit preset or targets were provided
    if not target_preset and not target and not files_list:
        bound_preset = settings_mgr.get_bound_preset(current_folder)
        if bound_preset:
            target_preset = bound_preset
            console.print(f"[dim]🔗 Auto-detected bound preset for folder: {bound_preset}[/dim]")

    config: Optional[PresetConfig] = None

    # Load preset if resolved
    if target_preset:
        config = preset_mgr.load_preset(target_preset)
        if not config:
            console.print(f"[red]❌ Preset '{target_preset}' not found in {preset_mgr.presets_dir}![/red]")
            raise typer.Exit(1)
        console.print(f"[green]Loaded preset:[/green] {target_preset}")

        if directory is not None:
            config.root_path = str(directory.resolve())
        if output is not None:
            config.output_file = str(output)

        saved_settings.last_preset = target_preset
        settings_mgr.save(saved_settings)
    else:
        # Check for local .codewrap.json file
        local_config = preset_mgr.load_local_config(current_folder)
        if local_config and not target and not files_list:
            config = local_config
            console.print(f"[dim]📄 Auto-loaded local config (.codewrap.json)[/dim]")
        else:
            rules = [parse_target_arg(t) for t in target] if target else []

            if files_list is not None:
                fl_path = files_list if files_list.is_absolute() else current_folder / files_list
                if fl_path.exists():
                    for line in fl_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            rules.append(parse_target_arg(line))
                else:
                    console.print(f"[yellow]⚠️ File list '{files_list}' not found.[/yellow]")

            root = infer_common_root(rules, current_folder)

            config = PresetConfig(
                root_path=str(root),
                targets=rules,
                output_file=str(output) if output else None,
                copy_to_clipboard=saved_settings.copy_to_clipboard,
                use_numbering=saved_settings.use_numbering,
                save_in_cwd=saved_settings.save_in_cwd,
            )

    # Save preset if requested
    if save_preset:
        config.name = save_preset
        saved_path = preset_mgr.save_preset(config, save_preset)
        console.print(f"[bold green]Saved preset:[/bold green] {save_preset} ({saved_path})")
        if bind:
            settings_mgr.bind_folder(current_folder, save_preset)
            console.print(f"[bold cyan]🔗 Bound folder '{current_folder}' to preset '{save_preset}'[/bold cyan]")

    # Create local config if requested
    if init_config:
        local_file = preset_mgr.init_local_config(current_folder, config)
        console.print(f"[bold green]Created local config file:[/bold green] {local_file}")

    engine = CodeProcessorEngine(config)

    def cli_progress(path: Path, tokens: int, total_tokens: int):
        console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")

    console.print(f"[bold blue]🛠 Gathering context for:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=cli_progress)

    console.print(f"\n[bold green]✅ Done![/bold green] Files: {files} | Tokens (≈): [cyan]{tokens}[/cyan]")
    console.print(f"📂 Result saved to: [bold underline]{engine.output_file}[/bold underline]")

    if config.copy_to_clipboard:
        try:
            import pyperclip
            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print("[bold green]📋 Content successfully copied to clipboard![/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not copy to clipboard: {e}[/yellow]")