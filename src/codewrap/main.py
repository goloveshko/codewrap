import os
from pathlib import Path
from typing import List, Optional
import typer
from rich.console import Console

app = typer.Typer(help="CodeWrap: Конвертируйте ваш код в один Markdown файл для LLM.")
console = Console()


class CodeProcessor:
    """Класс для обработки файлов и формирования Markdown контента."""

    def __init__(self, root_path: Path, extensions: List[str], output_file: Path):
        self.root_path = root_path
        self.extensions = [ext.lower().strip(".") for ext in extensions]
        self.output_file = output_file

    def _get_language(self, extension: str) -> str:
        """Маппинг расширений в языки для подсветки Markdown."""
        mapping = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "cpp": "cpp",
            "c": "c",
            "h": "cpp",
            "rs": "rust",
            "go": "go",
            "html": "html",
            "css": "css",
            "kt": "kotlin",
        }
        return mapping.get(extension.lower(), extension)

    def process(self):
        """Основной цикл обработки."""
        count = 0
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Project Context: {self.root_path.name}\n\n")
            f.write("Generated for LLM analysis.\n\n---\n")

            # Рекурсивный обход папки
            for path in self.root_path.rglob("*"):
                if (
                    path.is_file()
                    and path.suffix.lower().lstrip(".") in self.extensions
                ):
                    # Пропускаем скрытые папки (типа .git, .venv)
                    if any(part.startswith(".") for part in path.parts):
                        continue

                    self._write_file_to_md(path, f)
                    count += 1

        return count

    def _write_file_to_md(self, file_path: Path, output_stream):
        """Читает файл и записывает его в поток в формате Markdown."""
        relative_path = file_path.relative_to(self.root_path)
        lang = self._get_language(file_path.suffix.lstrip("."))

        try:
            content = file_path.read_text(encoding="utf-8")
            output_stream.write(f"## File: {relative_path}\n")
            output_stream.write(f"```{lang}\n")
            output_stream.write(content)
            output_stream.write("\n```\n\n")
            console.print(f"[green]✔[/green] Added: {relative_path}")
        except Exception as e:
            console.print(f"[red]✘[/red] Error reading {relative_path}: {e}")


@app.command()
def main(
    directory: Path = typer.Argument(
        Path("."),  # Теперь по умолчанию текущая папка
        help="Путь к папке с исходниками (по умолчанию текущая)",
    ),
    extensions: str = typer.Option(
        "py,js,ts,cpp,h", "--ext", "-e", help="Список расширений через запятую"
    ),
    output: Path = typer.Option(
        "context.md", "--output", "-o", help="Имя итогового файла"
    ),
):
    # Проверка существования пути
    if not directory.exists():
        console.print(f"[bold red]Ошибка:[/bold red] Путь {directory} не существует.")
        raise typer.Exit(code=1)

    # Конвертируем в абсолютный путь для красоты логов
    directory = directory.resolve()

    if not directory.is_dir():
        console.print(
            f"[bold red]Ошибка:[/bold red] Путь {directory} не является папкой."
        )
        raise typer.Exit(code=1)

    ext_list = [e.strip() for e in extensions.split(",")]
    processor = CodeProcessor(directory, ext_list, output)

    console.print(f"[bold blue]🚀 Начинаю сборку кода из:[/bold blue] {directory}")
    total = processor.process()

    console.print(f"\n[bold green]✨ Готово![/bold green] Обработано файлов: {total}")
    console.print(f"📦 Результат: [bold cyan]{output.resolve()}[/bold cyan]")


if __name__ == "__main__":
    app()
