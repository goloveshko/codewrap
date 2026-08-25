import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class AppSettings(BaseModel):
    """Global application settings stored in ~/.codewrap/settings.json."""

    tokenizer: str = "o200k_base"
    exclude_binary: bool = True
    auto_rename_outputs: bool = False
    copy_to_clipboard: bool = False
    save_in_current_dir: bool = False
    presets_dir: str | None = None
    folder_bindings: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_settings(cls, data: dict) -> dict:
        """Migrate legacy configuration keys automatically."""
        if not isinstance(data, dict):
            return data
        if "encoding" in data and "tokenizer" not in data:
            data["tokenizer"] = data.pop("encoding")
        if "use_numbering" in data and "auto_rename_outputs" not in data:
            data["auto_rename_outputs"] = data.pop("use_numbering")
        if "save_in_cwd" in data and "save_in_current_dir" not in data:
            data["save_in_current_dir"] = data.pop("save_in_cwd")
        return data


class SettingsManager:
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
        except Exception as e:
            logger.warning("Failed to load %s (%s) — using default settings.", self.settings_file, e)
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

    def get_bound_preset(self, folder_path: Path) -> str | None:
        settings = self.load()
        resolved_key = str(folder_path.resolve())
        return settings.folder_bindings.get(resolved_key)
