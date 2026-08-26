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


def _scope_prefix(root: Path, scope: Path) -> str:
    """Root-relative posix path of scope ('' when scope is the repo root itself)."""
    try:
        rel = scope.resolve().relative_to(root)
    except ValueError:
        return ""
    text = str(rel)
    return "" if text == "." else text.replace("\\", "/")


def _parse_status_z(res: subprocess.CompletedProcess[str], base_path: Path) -> list[tuple[str, Path]]:
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
        path = base_path / record[3:]
        results.append((status_code, path))
        if "R" in record[:2] or "C" in record[:2]:
            i += 1
    return results


class GitHelper:
    """Lightweight Git CLI helper with zero external dependencies.

    All commands run against the repository top level (porcelain paths are
    root-relative), but results are scoped to the directory passed by the
    caller so invoking from a subfolder only covers that subfolder.
    """

    @staticmethod
    def get_repo_root(path: Path) -> Path | None:
        """Return the working tree top-level directory, or None if not a Git repo."""
        if not path.is_dir():
            return None
        res = _run_git(["rev-parse", "--show-toplevel"], path, check=False)
        if res is None or res.returncode != 0 or not res.stdout.strip():
            return None
        return Path(res.stdout.strip())

    @staticmethod
    def is_git_repo(path: Path) -> bool:
        return GitHelper.get_repo_root(path) is not None

    @staticmethod
    def get_tracked_files(repo_path: Path) -> list[Path]:
        """Tracked files under repo_path as absolute paths."""
        root = GitHelper.get_repo_root(repo_path)
        if root is None:
            return []
        args = ["ls-files", "-z"]
        prefix = _scope_prefix(root, repo_path)
        if prefix:
            args += ["--", prefix]
        res = _run_git(args, root)
        if res is None:
            return []
        return [root / f for f in res.stdout.split("\0") if f]

    @staticmethod
    def get_modified_files(repo_path: Path) -> list[Path]:
        root = GitHelper.get_repo_root(repo_path)
        if root is None:
            return []
        res = _run_git(GitHelper._status_args(root, repo_path), root)
        if res is None:
            return []
        return [p for _, p in _parse_status_z(res, root)]

    @staticmethod
    def get_files_since(repo_path: Path, since_arg: str) -> list[Path]:
        root = GitHelper.get_repo_root(repo_path)
        if root is None:
            return []
        args = ["log", f"--since={since_arg}", "--name-only", "--pretty=format:", "-z"]
        prefix = _scope_prefix(root, repo_path)
        if prefix:
            args += ["--", prefix]
        res = _run_git(args, root)
        if res is None:
            return []
        unique_files = {f for f in res.stdout.split("\0") if f}
        return sorted(root / f for f in unique_files)

    @staticmethod
    def get_diff_text(repo_path: Path, ref: str | None = None) -> str:
        """Returns unified diff scoped to repo_path (staged + unstaged, or vs a given ref)."""
        root = GitHelper.get_repo_root(repo_path)
        if root is None:
            return ""
        prefix = _scope_prefix(root, repo_path)

        def _scoped(base: list[str]) -> list[str]:
            return base + (["--", prefix] if prefix else [])

        if ref:
            res = _run_git(_scoped(["diff", ref]), root)
            return "" if res is None else res.stdout
        res = _run_git(_scoped(["diff", "HEAD"]), root)
        if res is not None:
            return res.stdout
        parts = [
            r.stdout
            for r in (_run_git(_scoped(["diff", "--cached"]), root), _run_git(_scoped(["diff"]), root))
            if r is not None
        ]
        return "\n".join(parts)

    @staticmethod
    def get_status_files(repo_path: Path) -> list[tuple[str, Path]]:
        """Returns list of (status_code, absolute_path) for changes under repo_path,
        e.g. [('M', path1), ('??', path2)]. Safe to call from any subdirectory."""
        root = GitHelper.get_repo_root(repo_path)
        if root is None:
            return []
        res = _run_git(GitHelper._status_args(root, repo_path), root)
        if res is None:
            return []
        return _parse_status_z(res, root)

    @staticmethod
    def get_file_diff(file_path: Path) -> str:
        """Returns git diff vs HEAD for an absolute file path inside a repository."""
        target = file_path.resolve()
        root = GitHelper.get_repo_root(target.parent)
        if root is None:
            return ""
        try:
            rel = target.relative_to(root)
        except ValueError:
            return ""
        res = _run_git(["diff", "HEAD", "--", str(rel)], root)
        return "" if res is None else res.stdout

    @staticmethod
    def _status_args(root: Path, scope: Path) -> list[str]:
        args = ["status", "--porcelain", "-z"]
        prefix = _scope_prefix(root, scope)
        if prefix:
            args += ["--", prefix]
        return args
