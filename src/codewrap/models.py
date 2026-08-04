from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class TargetRule(BaseModel):
    path: str
    extensions: List[str] = Field(default_factory=list)


class PresetConfig(BaseModel):
    name: Optional[str] = None
    root_path: str = "."
    targets: List[TargetRule] = Field(default_factory=list)
    output_file: Optional[str] = None
    encoding: str = "o200k_base"
    respect_gitignore: bool = True
    include_tree: bool = True
    copy_to_clipboard: bool = False
    use_numbering: bool = False
    save_in_cwd: bool = False
