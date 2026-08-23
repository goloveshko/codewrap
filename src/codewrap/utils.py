import os
from pathlib import Path

from codewrap.models import TargetRule

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".svg",
    ".tiff",
    ".psd",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".pyc",
    ".o",
    ".a",
    ".class",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".bz2",
    ".xz",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
}


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary using extension and null-byte buffer inspection."""
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True

    return False


def parse_target_arg(target_str: str) -> TargetRule:
    """Parse target rule string into a TargetRule object, accounting for Windows drive letters."""
    target_str = target_str.strip()
    last_colon = target_str.rfind(":")
    if last_colon > 1:
        exts_part = target_str[last_colon + 1 :].strip()
        if "/" not in exts_part and "\\" not in exts_part:
            path_part = target_str[:last_colon].strip()
            exts = [e.strip() for e in exts_part.split(",") if e.strip()]
            return TargetRule(path=path_part, extensions=exts)
    return TargetRule(path=target_str)


def infer_common_root(rules: list[TargetRule], default_root: Path) -> Path:
    """Infer the common parent directory for a list of target rules."""
    roots: list[str] = []
    for r in rules:
        p = Path(r.path)
        if not p.is_absolute():
            p = default_root / p
        base = p.parent if p.is_file() else p
        roots.append(os.path.normcase(str(base)))

    if not roots:
        return default_root.resolve()

    try:
        common = os.path.commonpath(roots)
    except ValueError:
        # Paths on different drives (Windows) have no common root.
        return default_root.resolve()

    common_path = Path(common)
    if not common_path.is_absolute():
        return (default_root / common_path).resolve()
    return common_path.resolve()
