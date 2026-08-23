import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, logging failures instead of silently swallowing them."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )
    except FileNotFoundError:
        logger.warning("Git executable not found in PATH. Git-based detection is disabled.")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        logger.warning("git %s failed: %s", " ".join(args), stderr or e)
    except OSError as e:
        logger.warning("Failed to execute git %s: %s", " ".join(args), e)
    return None


class GitHelper:
    """Lightweight Git CLI helper with zero external dependencies."""

    @staticmethod
    def is_git_repo(path: Path) -> bool:
        if not path.is_dir():
            return False
        res = _run_git(["rev-parse", "--is-inside-work-tree"], path, check=False)
        return res is not None and res.returncode == 0 and res.stdout.strip() == "true"

    @staticmethod
    def get_tracked_files(repo_path: Path) -> list[Path]:
        if not repo_path.is_dir():
            return []
        res = _run_git(["ls-files"], repo_path)
        if res is None:
            return []
        lines = res.stdout.splitlines()
        return [repo_path / line.strip() for line in lines if line.strip()]

    @staticmethod
    def get_modified_files(repo_path: Path) -> list[Path]:
        if not repo_path.is_dir():
            return []
        res = _run_git(["status", "--porcelain"], repo_path)
        if res is None:
            return []
        files: list[Path] = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            parts = line[3:].strip().split(" -> ")
            target_file = parts[-1]
            files.append(repo_path / target_file)
        return files

    @staticmethod
    def get_files_since(repo_path: Path, since_arg: str) -> list[Path]:
        if not repo_path.is_dir():
            return []
        res = _run_git(["log", f"--since={since_arg}", "--name-only", "--pretty=format:"], repo_path)
        if res is None:
            return []
        unique_files = {line.strip() for line in res.stdout.splitlines() if line.strip()}
        return [repo_path / f for f in unique_files]

    @staticmethod
    def get_diff_text(repo_path: Path, ref: str | None = None) -> str:
        if not repo_path.is_dir():
            return ""
        cmd = ["diff"]
        if ref:
            cmd.append(ref)
        res = _run_git(cmd, repo_path)
        return "" if res is None else res.stdout

    @staticmethod
    def get_status_files(repo_path: Path) -> list[tuple[str, Path]]:
        """Returns list of (status_code, file_path) e.g. [('M', path1), ('??', path2)]."""
        if not repo_path.is_dir():
            return []
        res = _run_git(["status", "--porcelain"], repo_path)
        if res is None:
            return []
        results: list[tuple[str, Path]] = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            status_code = line[:2].strip()
            parts = line[3:].strip().split(" -> ")
            target_file = parts[-1]
            results.append((status_code, repo_path / target_file))
        return results

    @staticmethod
    def get_file_diff(repo_path: Path, relative_file_path: Path) -> str:
        """Returns git diff for a specific file."""
        if not repo_path.is_dir():
            return ""
        res = _run_git(["diff", "HEAD", "--", str(relative_file_path)], repo_path)
        return "" if res is None else res.stdout
