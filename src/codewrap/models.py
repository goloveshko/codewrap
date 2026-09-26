from pydantic import BaseModel, Field


class TargetRule(BaseModel):
    """Rule defining a path (file or directory) and optional extension filters."""

    path: str
    extensions: list[str] = Field(default_factory=list)


class ScanConfig(BaseModel):
    """Resolved configuration for a single scan run."""

    root_path: str = "."
    targets: list[TargetRule] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    output_file: str | None = None
    tokenizer: str = "o200k_base"
    copy_to_clipboard: bool = False
    auto_rename_outputs: bool = False
    save_in_current_dir: bool = False
