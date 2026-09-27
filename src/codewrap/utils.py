import os
import re
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


def format_size(num_bytes: int) -> str:
    """Human-readable byte size, e.g. '812 B' or '12.3 KB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(b|kb|mb|gb)?$", re.IGNORECASE)
_SIZE_MULTIPLIERS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def parse_size_arg(value: str) -> int:
    """Parse a size like '512kb', '2mb' or a plain byte count. 0 means 'no limit'.

    Raises ValueError for malformed values so CLI layers can report them.
    """
    match = _SIZE_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid size '{value}'; use a byte count or a kb/mb/gb suffix, e.g. '512kb'")
    number, unit = match.groups()
    return int(float(number) * _SIZE_MULTIPLIERS[(unit or "b").lower()])


def parse_split_arg(value: str) -> tuple[int, str]:
    """Parse a --split budget: a bare number means tokens, a size suffix means bytes.

    Returns (amount, unit) where unit is 'tokens' or 'bytes'. Raises ValueError
    for malformed or non-positive values.
    """
    cleaned = value.strip().replace(" ", "").lower()
    amount: int
    unit: str
    if cleaned.isdigit():
        amount, unit = int(cleaned), "tokens"
    else:
        try:
            amount = parse_size_arg(cleaned)
        except ValueError:
            raise ValueError(
                f"invalid --split value '{value}'; use a token count like '50000' or a size like '256kb'"
            ) from None
        unit = "bytes"
    if amount <= 0:
        raise ValueError("split budget must be greater than 0")
    return amount, unit


# Bytes inspected when sniffing file content; larger samples slow scans for
# negligible accuracy gains on text-vs-binary classification.
SNIFF_SAMPLE_BYTES = 8192
_CONTROL_ALLOWED = set("\t\n\r\x0b\x0c")


def is_binary_bytes(data: bytes) -> bool:
    """Classify content by sniffing: NUL bytes, failed UTF-8, or many control chars."""
    sample = data[:SNIFF_SAMPLE_BYTES]
    if b"\x00" in sample:
        return True
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.reason != "unexpected end of data":
            return True
        # The sample merely cut a multi-byte character in half; judge the valid prefix.
        text = sample[: e.start].decode("utf-8")
    if not text:
        return False
    non_printable = sum(1 for ch in text if not ch.isprintable() and ch not in _CONTROL_ALLOWED)
    return non_printable / len(text) > 0.30


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
