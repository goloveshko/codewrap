from pydantic import BaseModel, Field


class TargetRule(BaseModel):
    """Rule defining a path (file or directory) and optional extension filters."""

    path: str
    extensions: list[str] = Field(default_factory=list)


class PresetConfig(BaseModel):
    """Configuration structure for preset contexts."""

    name: str | None = None
    root_path: str = "."
    targets: list[TargetRule] = Field(default_factory=list)
    output_file: str | None = None
    encoding: str = "o200k_base"
    copy_to_clipboard: bool = False
    use_numbering: bool = False
    save_in_cwd: bool = False
