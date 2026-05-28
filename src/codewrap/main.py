import os
from pathlib import Path
from typing import List, Optional
import typer
import pathspec
import tiktoken
from rich.console import Console
from rich.tree import Tree
import re
from urllib3.exceptions import ConnectTimeoutError
import requests

app = typer.Typer(help="CodeWrap: Профессиональный сборщик контекста для LLM.")
console = Console()


class CodeProcessor:
    def __init__(self, root_path: Path, extensions: List[str], output_file: Path):
        self.root_path = root_path.resolve()
        self.extensions = [ext.lower().strip(".") for ext in extensions]
        self.output_file = output_file
        self.ignore_spec = self._load_gitignore()
        try:
            self.tokenizer = tiktoken.get_encoding(
                "cl100k_base"
            )  # Токенайзер для GPT-4/o
        except (ConnectTimeoutError, requests.exceptions.ConnectTimeout) as e:
            console.print(
                "[red]❌ Не удалось загрузить токенизатор. Укажите прокси с --proxy или настройте локальный кэш.[/red]"
            )
            raise typer.Exit(1) from e

    def _load_gitignore(self) -> pathspec.PathSpec:
        """Загружает .gitignore и создает объект для фильтрации."""
        ignore_file = self.root_path / ".gitignore"
        patterns = [
            ".git/",
            ".venv/",
            "__pycache__/",
            ".DS_Store",
            "node_modules/",
        ]  # Базовые игноры

        if ignore_file.exists():
            patterns.extend(ignore_file.read_text().splitlines())

        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, path: Path) -> bool:
        """Проверяет, должен ли файл быть проигнорирован."""
        relative_path = path.relative_to(self.root_path)
        # Проверяем расширение, если это файл
        if path.is_file():
            if path.suffix.lower().lstrip(".") not in self.extensions:
                return True
        return self.ignore_spec.match_file(str(relative_path))

    def generate_tree(self, current_path: Path, tree: Optional[Tree] = None) -> Tree:
        """Рекурсивно строит дерево каталогов с учетом игнорирования."""
        if tree is None:
            tree = Tree(f"📂 [bold blue]{current_path.name}[/bold blue]")

        # Сортируем: сначала папки, потом файлы
        paths = sorted(current_path.iterdir(), key=lambda p: (p.is_file(), p.name))

        for path in paths:
            if self.is_ignored(path):
                continue

            if path.is_dir():
                branch = tree.add(f"📁 {path.name}")
                self.generate_tree(path, branch)
            else:
                tree.add(f"📄 {path.name}")

        return tree

    def _get_language(self, extension: str) -> str:
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
        total_tokens = 0
        file_count = 0

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Project Context: {self.root_path.name}\n\n")

            # Добавляем Tree View
            console.print("[yellow]Building Tree View...[/yellow]")
            tree = self.generate_tree(self.root_path)
            # Мы можем отрендерить дерево прямо в строку для файла
            from rich.console import Console as StringConsole

            string_console = StringConsole(width=80, force_terminal=False)
            with string_console.capture() as capture:
                string_console.print(tree)

            f.write("## Directory Structure\n```text\n")
            f.write(capture.get())
            f.write("```\n\n---\n")

            # Обход и запись файлов
            for path in self.root_path.rglob("*"):
                if path.is_file() and not self.is_ignored(path):
                    content = path.read_text(encoding="utf-8", errors="replace")

                    # Считаем токены
                    tokens = len(self.tokenizer.encode(content))
                    total_tokens += tokens
                    file_count += 1

                    relative_path = path.relative_to(self.root_path)
                    lang = self._get_language(path.suffix.lstrip("."))

                    f.write(f"## File: {relative_path}\n")
                    f.write(f"<!-- Tokens: {tokens} -->\n")
                    f.write(f"```{lang}\n")
                    f.write(content)
                    f.write("\n```\n\n")

                    console.print(
                        f"[green]✔[/green] {relative_path} [dim]({tokens} tokens)[/dim]"
                    )

        return file_count, total_tokens


def slugify(text: str) -> str:
    """Очищает строку от спецсимволов, оставляя только буквы, цифры и подчеркивания."""
    return re.sub(r"[^\w\-]", "_", text).strip("_")


def generate_output_name(directory: Path) -> Path:
    """Генерирует имя файла на основе пути к папке."""
    abs_path = directory.resolve()
    # Берем последние две части пути (например, 'work' и 'project-api')
    parts = abs_path.parts

    # Отфильтровываем корень (типа 'C:\' или '/')
    useful_parts = [
        p for p in parts if p and not p.endswith(os.path.sep) and ":" not in p
    ]

    # Берем последние два элемента, если их много, иначе один
    relevant_parts = useful_parts[-2:] if len(useful_parts) >= 2 else useful_parts[-1:]

    # Очищаем и соединяем
    base_name = "_".join(slugify(p) for p in relevant_parts)
    return Path(f"{base_name}_context.md")


@app.command()
def main(
    directory: Path = typer.Argument(Path("."), help="Папка проекта"),
    extensions: str = typer.Option("py,js,ts,cpp,h,toml,md", "--ext", "-e"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Имя файла (генерируется автоматически, если не указано)",
    ),
    proxy: Optional[str] = typer.Option(
        None,
        "--proxy",
        "-p",
        help="Прокси-сервер, например http://proxy.example.com:8080",
    ),
):
    if not directory.is_dir():
        console.print("[bold red]Ошибка: Путь не найден[/bold red]")
        raise typer.Exit(1)

    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        console.print(f"[yellow]🌐 Используется прокси: {proxy}[/yellow]")

    # ДИНАМИЧЕСКОЕ ИМЯ: Если output не задан, генерируем его
    actual_output = output if output is not None else generate_output_name(directory)

    processor = CodeProcessor(directory, extensions.split(","), actual_output)

    console.print(
        f"[bold blue]🛠  CodeWrap запущен для:[/bold blue] {directory.resolve()}"
    )
    files, tokens = processor.process()

    console.print("\n[bold green]✅ Готово![/bold green]")
    console.print(f"📄 Файлов обработано: [bold]{files}[/bold]")
    console.print(f"🧬 Всего токенов (≈): [bold cyan]{tokens}[/bold cyan]")
    console.print(
        f"📂 Результат: [bold underline]{actual_output.resolve()}[/bold underline]"
    )


if __name__ == "__main__":
    app()
