from pydantic import BaseModel, Field, model_validator


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
    tokenizer: str = "o200k_base"
    copy_to_clipboard: bool = False
    auto_rename_outputs: bool = False
    save_in_current_dir: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_keys(cls, data: dict) -> dict:
        """Seamlessly migrate legacy keys from older preset versions."""
        if not isinstance(data, dict):
            return data
        # Legacy name migrations
        if "encoding" in data and "tokenizer" not in data:
            data["tokenizer"] = data.pop("encoding")
        if "use_numbering" in data and "auto_rename_outputs" not in data:
            data["auto_rename_outputs"] = data.pop("use_numbering")
        if "save_in_cwd" in data and "save_in_current_dir" not in data:
            data["save_in_current_dir"] = data.pop("save_in_cwd")
        return data
