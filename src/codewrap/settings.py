import json
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """Global user settings stored in ~/.codewrap/settings.json."""
    presets_dir: Optional[str] = None
    use_numbering: bool = False
    copy_to_clipboard: bool = False
    save_in_cwd: bool = False
    last_preset: Optional[str] = None
    # Maps folder paths to bound preset names (Zero-Clutter folder binding)
    folder_bindings: Dict[str, str] = Field(default_factory=dict)


class SettingsManager:
    """Manages reading and persisting application settings."""

    def __init__(self) -> None:
        self.config_dir = Path.home() / ".codewrap"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.config_dir / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_file.exists():
            return AppSettings()
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return AppSettings.model_validate(data)
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        data = settings.model_dump(mode="json")
        self.settings_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> AppSettings:
        if self.settings_file.exists():
            self.settings_file.unlink()
        return AppSettings()

    def bind_folder(self, folder_path: Path, preset_name: str) -> None:
        settings = self.load()
        resolved_key = str(folder_path.resolve())
        settings.folder_bindings[resolved_key] = preset_name
        self.save(settings)

    def get_bound_preset(self, folder_path: Path) -> Optional[str]:
        settings = self.load()
        resolved_key = str(folder_path.resolve())
        return settings.folder_bindings.get(resolved_key)