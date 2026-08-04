from pathlib import Path
from typing import List, Optional
from rich.console import Console
import typer

from codewrap.engine import CodeProcessorEngine
from codewrap.models import PresetConfig, TargetRule
from codewrap.presets import PresetManager
from codewrap.settings import SettingsManager

app = typer.Typer(
    help="CodeWrap: Профессиональный сборщик контекста исходного кода для LLM.",
    add_completion=False,
)
console = Console()


def parse_target_arg(target_str: str) -> TargetRule:
    target_str = target_str.strip()
    last_colon = target_str.rfind(":")
    if last_colon > 1:
        exts_part = target_str[last_colon + 1 :].strip()
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
        None, help="Корень проекта (по умолчанию из настроек/пресета или текущая папка)"
    ),
    target: Optional[List[str]] = typer.Option(
        None, "--target", "-t", help="Таргеты 'folder:py,toml' или 'path/file.py'"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Выходной файл"),
    preset: Optional[str] = typer.Option(
        None, "--preset", "-p", help="Загрузить указанный пресет"
    ),
    save_preset: Optional[str] = typer.Option(
        None, "--save-preset", "-sp", "-s", help="Сохранить текущие параметры в пресет"
    ),
    last: bool = typer.Option(
        False, "--last", "-l", help="Запустить последний использованный пресет"
    ),
    presets_dir: Optional[Path] = typer.Option(
        None, "--presets-dir", "-pd", help="Кастомная папка с пресетами"
    ),
    list_presets: bool = typer.Option(
        False, "--list-presets", "-lp", help="Список доступных пресетов"
    ),
    numbered: Optional[bool] = typer.Option(
        None, "--numbered", "-n", help="Нумерация файлов (_1.md)"
    ),
    save_in_cwd: Optional[bool] = typer.Option(
        None, "--cwd", "-w", help="Сохранять итоговый файл в текущей папке терминала"
    ),
    copy: Optional[bool] = typer.Option(
        None, "--copy", "-c", help="Скопировать в буфер обмена"
    ),
    clear_settings: bool = typer.Option(
        False,
        "--clear-settings",
        "-cs",
        "--reset-config",
        help="Сбросить запомненные глобальные настройки",
    ),
) -> None:
    settings_mgr = SettingsManager()

    if clear_settings:
        settings_mgr.reset()
        console.print(
            "[bold green]🧹 Глобальные настройки успешно сброшены![/bold green]"
        )
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

    effective_presets_dir = (
        Path(saved_settings.presets_dir) if saved_settings.presets_dir else None
    )
    preset_mgr = PresetManager(custom_dir=effective_presets_dir)

    if list_presets:
        presets = preset_mgr.list_presets()
        if not presets:
            console.print(
                f"[yellow]Пресеты не найдены в: {preset_mgr.presets_dir}[/yellow]"
            )
        else:
            console.print(
                f"[bold blue]Доступные пресеты ({preset_mgr.presets_dir}):[/bold blue]"
            )
            for p in presets:
                console.print(f"  • {p}")
        return

    target_preset = preset
    if last:
        if not saved_settings.last_preset:
            console.print("[red]❌ Нет сохраненного последнего пресета![/red]")
            raise typer.Exit(1)
        target_preset = saved_settings.last_preset

    if target_preset:
        config = preset_mgr.load_preset(target_preset)
        if not config:
            console.print(
                f"[red]❌ Пресет '{target_preset}' не найден в {preset_mgr.presets_dir}![/red]"
            )
            raise typer.Exit(1)
        console.print(f"[green]Загружен пресет:[/green] {target_preset}")

        if directory is not None:
            config.root_path = str(directory.resolve())
        if output is not None:
            config.output_file = str(output)

        saved_settings.last_preset = target_preset
        settings_mgr.save(saved_settings)
    else:
        rules = [parse_target_arg(t) for t in target] if target else []
        default_dir = directory or Path(".")
        root = infer_common_root(rules, default_dir)

        config = PresetConfig(
            root_path=str(root),
            targets=rules,
            output_file=str(output) if output else None,
            copy_to_clipboard=saved_settings.copy_to_clipboard,
            use_numbering=saved_settings.use_numbering,
            save_in_cwd=saved_settings.save_in_cwd,
        )

    if save_preset:
        config.name = save_preset
        saved_path = preset_mgr.save_preset(config, save_preset)
        console.print(
            f"[bold green]Сохранен пресет:[/bold green] {save_preset} ({saved_path})"
        )

    engine = CodeProcessorEngine(config)

    def cli_progress(path: Path, tokens: int, total_tokens: int):
        console.print(f"[green]✔[/green] {path} [dim]({tokens} tokens)[/dim]")

    console.print(f"[bold blue]🛠 Сборка контекста для:[/bold blue] {engine.root_path}")
    files, tokens = engine.process(progress_callback=cli_progress)

    console.print(
        f"\n[bold green]✅ Готово![/bold green] Файлов: {files} | Токенов (≈): [cyan]{tokens}[/cyan]"
    )
    console.print(
        f"📂 Результат: [bold underline]{engine.output_file}[/bold underline]"
    )

    if config.copy_to_clipboard:
        try:
            import pyperclip

            pyperclip.copy(engine.output_file.read_text(encoding="utf-8"))
            console.print("[bold green]📋 Скопировано в буфер обмена![/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Не удалось скопировать в буфер: {e}[/yellow]")
