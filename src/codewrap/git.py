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
            encoding="utf-8",
            errors="replace",
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


def _parse_status_z(res: subprocess.CompletedProcess[str], repo_path: Path) -> list[tuple[str, Path]]:
    """Parse 'git status --porcelain -z' output into (status_code, path) pairs.

    In -z format entries are NUL-separated, paths are never quoted, and
    rename/copy records are followed by an extra field with the original path.
    """
    results: list[tuple[str, Path]] = []
    records = res.stdout.split("\0")
    i = 0
    while i < len(records):
        record = records[i]
        i += 1
        if len(record) < 4:
            continue
        status_code = record[:2].strip()
        path = repo_path / record[3:]
        results.append((status_code, path))
        if "R" in record[:2] or "C" in record[:2]:
            i += 1
    return results


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
        res = _run_git(["ls-files", "-z"], repo_path)
        if res is None:
            return []
        return [repo_path / f for f in res.stdout.split("\0") if f]

    @staticmethod
    def get_modified_files(repo_path: Path) -> list[Path]:
        if not repo_path.is_dir():
            return []
        res = _run_git(["status", "--porcelain", "-z"], repo_path)
        if res is None:
            return []
        return [p for _, p in _parse_status_z(res, repo_path)]

    @staticmethod
    def get_files_since(repo_path: Path, since_arg: str) -> list[Path]:
        if not repo_path.is_dir():
            return []
        res = _run_git(["log", f"--since={since_arg}", "--name-only", "--pretty=format:", "-z"], repo_path)
        if res is None:
            return []
        unique_files = {f for f in res.stdout.split("\0") if f}
        return sorted(repo_path / f for f in unique_files)

    @staticmethod
    def get_diff_text(repo_path: Path, ref: str | None = None) -> str:
        """Returns unified diff of uncommitted changes (staged + unstaged) or vs a given ref."""
        if not repo_path.is_dir():
            return ""
        if ref:
            res = _run_git(["diff", ref], repo_path)
            return "" if res is None else res.stdout
        res = _run_git(["diff", "HEAD"], repo_path)
        if res is not None:
            return res.stdout
        parts = [
            r.stdout
            for r in (_run_git(["diff", "--cached"], repo_path), _run_git(["diff"], repo_path))
            if r is not None
        ]
        return "\n".join(parts)

    @staticmethod
    def get_status_files(repo_path: Path) -> list[tuple[str, Path]]:
        """Returns list of (status_code, file_path) e.g. [('M', path1), ('??', path2)]."""
        if not repo_path.is_dir():
            return []
        res = _run_git(["status", "--porcelain", "-z"], repo_path)
        if res is None:
            return []
        return _parse_status_z(res, repo_path)

    @staticmethod
    def get_file_diff(repo_path: Path, relative_file_path: Path) -> str:
        """Returns git diff for a specific file."""
        if not repo_path.is_dir():
            return ""
        res = _run_git(["diff", "HEAD", "--", str(relative_file_path)], repo_path)
        return "" if res is None else res.stdout
