from pathlib import Path
import subprocess
from typing import List, Optional


class GitHelper:
    """Lightweight Git CLI helper with zero external dependencies."""

    @staticmethod
    def is_git_repo(path: Path) -> bool:
        if not path.is_dir():
            return False
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    @staticmethod
    def get_tracked_files(repo_path: Path) -> List[Path]:
        if not repo_path.is_dir():
            return []
        try:
            res = subprocess.run(
                ["git", "ls-files"],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            lines = res.stdout.splitlines()
            return [repo_path / line.strip() for line in lines if line.strip()]
        except Exception:
            return []

    @staticmethod
    def get_modified_files(repo_path: Path) -> List[Path]:
        if not repo_path.is_dir():
            return []
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            files: List[Path] = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line[3:].strip().split(" -> ")
                target_file = parts[-1]
                files.append(repo_path / target_file)
            return files
        except Exception:
            return []

    @staticmethod
    def get_files_since(repo_path: Path, since_arg: str) -> List[Path]:
        if not repo_path.is_dir():
            return []
        try:
            res = subprocess.run(
                [
                    "git",
                    "log",
                    f"--since={since_arg}",
                    "--name-only",
                    "--pretty=format:",
                ],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            unique_files = {
                line.strip() for line in res.stdout.splitlines() if line.strip()
            }
            return [repo_path / f for f in unique_files]
        except Exception:
            return []

    @staticmethod
    def get_diff_text(repo_path: Path, ref: Optional[str] = None) -> str:
        if not repo_path.is_dir():
            return ""
        try:
            cmd = ["git", "diff"]
            if ref:
                cmd.append(ref)
            res = subprocess.run(
                cmd,
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            return res.stdout
        except Exception:
            return ""

    @staticmethod
    def get_status_files(repo_path: Path) -> List[Tuple[str, Path]]:
        """Returns list of (status_code, file_path) e.g. [('M', path1), ('??', path2)]."""
        if not repo_path.is_dir():
            return []
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            results: List[Tuple[str, Path]] = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                parts = line[3:].strip().split(" -> ")
                target_file = parts[-1]
                results.append((status_code, repo_path / target_file))
            return results
        except Exception:
            return []

    @staticmethod
    def get_file_diff(repo_path: Path, relative_file_path: Path) -> str:
        """Returns git diff for a specific file."""
        if not repo_path.is_dir():
            return ""
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD", "--", str(relative_file_path)],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            return res.stdout
        except Exception:
            return ""
