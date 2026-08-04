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
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except (ConnectTimeoutError, requests.exceptions.ConnectTimeout) as e:
            console.print(
                "[red]❌ Не удалось загрузить токенизатор. Укажите прокси с --proxy или настройте локальный кэш.[/red]"
            )
            raise typer.Exit(1) from e

    def _load_gitignore(self) -> pathspec.PathSpec:
        ignore_file = self.root_path / ".gitignore"
        patterns = [
            ".git/",
            ".venv/",
            "__pycache__/",
            ".DS_Store",
            "node_modules/",
        ]
        if ignore_file.exists():
            patterns.extend(ignore_file.read_text().splitlines())
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, path: Path) -> bool:
        relative_path = path.relative_to(self.root_path)
        if path.is_file():
            if path.suffix.lower().lstrip(".") not in self.extensions:
                return True
        return self.ignore_spec.match_file(str(relative_path))

    def is_ignored_only_gitignore(self, path: Path) -> bool:
        relative_path = path.relative_to(self.root_path)
        return self.ignore_spec.match_file(str(relative_path))

    def generate_tree(self, current_path: Path, tree: Optional[Tree] = None) -> Tree:
        if tree is None:
            tree = Tree(f"📂 [bold blue]{current_path.name}[/bold blue]")
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
            "toml": "toml",
            "md": "markdown",
        }
        return mapping.get(extension.lower(), extension)

    def process(
        self,
        files_list: Optional[List[Path]] = None,
        respect_gitignore: bool = True,
        include_tree: bool = True,
    ):
        total_tokens = 0
        file_count = 0

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(f"# Project Context: {self.root_path.name}\n\n")

            if include_tree:
                console.print("[yellow]Building Tree View...[/yellow]")
                tree = self.generate_tree(self.root_path)
                from rich.console import Console as StringConsole

                string_console = StringConsole(width=80, force_terminal=False)
                with string_console.capture() as capture:
                    string_console.print(tree)
                f.write("## Directory Structure\n```text\n")
                f.write(capture.get())
                f.write("```\n\n---\n")

            if files_list is None:
                all_files = []
                for path in self.root_path.rglob("*"):
                    if path.is_file() and not self.is_ignored(path):
                        all_files.append(path)
                all_files.sort()
                files_to_process = all_files
            else:
                files_to_process = []
                for file_path in files_list:
                    if file_path.is_absolute():
                        try:
                            file_path.relative_to(self.root_path)
                        except ValueError:
                            console.print(
                                f"[yellow]⚠️ Файл {file_path} находится вне корня проекта, пропускаем.[/yellow]"
                            )
                            continue
                    else:
                        full_path = (self.root_path / file_path).resolve()
                        if not full_path.exists():
                            console.print(
                                f"[yellow]⚠️ Файл {file_path} не найден, пропускаем.[/yellow]"
                            )
                            continue
                        file_path = full_path

                    if respect_gitignore and self.is_ignored_only_gitignore(file_path):
                        console.print(
                            f"[dim]⏭️ Файл {file_path.relative_to(self.root_path)} игнорируется .gitignore, пропускаем.[/dim]"
                        )
                        continue

                    files_to_process.append(file_path)

            for path in files_to_process:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    console.print(f"[red]❌ Не удалось прочитать {path}: {e}[/red]")
                    continue

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
    return re.sub(r"[^\w\-]", "_", text).strip("_")


def generate_output_name(directory: Path) -> Path:
    abs_path = directory.resolve()
    parts = abs_path.parts
    useful_parts = [
        p for p in parts if p and not p.endswith(os.path.sep) and ":" not in p
    ]
    relevant_parts = useful_parts[-2:] if len(useful_parts) >= 2 else useful_parts[-1:]
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
    files_list: Optional[Path] = typer.Option(
        None,
        "--files-list",
        "-f",
        help="Файл со списком файлов для обработки (по одному на строку, пути относительно directory)",
    ),
    respect_gitignore: bool = typer.Option(
        True,
        "--respect-gitignore/--no-respect-gitignore",
        help="Учитывать .gitignore при обработке списка",
    ),
    no_tree: bool = typer.Option(
        False,
        "--no-tree",
        help="Не включать в вывод дерево каталогов (особенно полезно при --files-list)",
    ),
):
    if not directory.is_dir():
        console.print("[bold red]Ошибка: Путь не найден[/bold red]")
        raise typer.Exit(1)

    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        console.print(f"[yellow]🌐 Используется прокси: {proxy}[/yellow]")

    # --- Обработка пути к файлу списка ---
    if files_list is not None:
        if not files_list.is_absolute():
            # Сначала ищем относительно папки проекта
            candidate = directory / files_list
            if candidate.exists():
                files_list = candidate
                console.print(
                    f"[dim]📂 Файл списка найден в папке проекта: {files_list}[/dim]"
                )
            else:
                # Если нет, пробуем как есть (относительно текущей папки) — для обратной совместимости
                if not files_list.exists():
                    console.print(
                        f"[red]❌ Файл списка {files_list} не найден ни в папке проекта, ни в текущей директории.[/red]"
                    )
                    raise typer.Exit(1)
        else:
            # Абсолютный путь – проверяем существование
            if not files_list.exists():
                console.print(f"[red]❌ Файл списка {files_list} не найден.[/red]")
                raise typer.Exit(1)

    # --- Определяем выходной файл ---
    if output is None:
        actual_output = generate_output_name(directory)
    else:
        # Если выходной путь относительный, помещаем его в папку проекта
        if not output.is_absolute():
            actual_output = directory / output
        else:
            actual_output = output

    # Создаём папку для выходного файла, если её нет
    actual_output.parent.mkdir(parents=True, exist_ok=True)

    # Читаем список файлов (если указан)
    file_paths = None
    if files_list is not None:
        with open(files_list, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            console.print("[yellow]⚠️ Файл списка пуст. Ничего не делаю.[/yellow]")
            raise typer.Exit(0)
        file_paths = [Path(line) for line in lines]

    processor = CodeProcessor(directory, extensions.split(","), actual_output)

    console.print(
        f"[bold blue]🛠  CodeWrap запущен для:[/bold blue] {directory.resolve()}"
    )

    files, tokens = processor.process(
        files_list=file_paths,
        respect_gitignore=respect_gitignore,
        include_tree=not no_tree,
    )

    console.print("\n[bold green]✅ Готово![/bold green]")
    console.print(f"📄 Файлов обработано: [bold]{files}[/bold]")
    console.print(f"🧬 Всего токенов (≈): [bold cyan]{tokens}[/bold cyan]")
    console.print(
        f"📂 Результат: [bold underline]{actual_output.resolve()}[/bold underline]"
    )


if __name__ == "__main__":
    app()
