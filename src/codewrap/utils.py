from pathlib import Path
from typing import List
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


def infer_common_root(rules: List[TargetRule], default_root: Path) -> Path:
    """Infer the common parent directory for a list of target rules."""
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
