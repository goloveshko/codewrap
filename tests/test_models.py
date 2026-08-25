"""Tests for configuration models, including backward compatibility and key migrations."""

from codewrap.models import PresetConfig


class TestPresetConfigCompat:
    def test_legacy_preset_with_dead_fields_still_loads(self):
        legacy = {
            "name": "old",
            "root_path": ".",
            "respect_gitignore": True,
            "include_tree": False,
        }
        config = PresetConfig.model_validate(legacy)
        assert config.name == "old"
        assert "respect_gitignore" not in PresetConfig.model_fields

    def test_legacy_key_migration(self):
        legacy = {
            "encoding": "cl100k_base",
            "use_numbering": True,
            "save_in_cwd": True,
        }
        config = PresetConfig.model_validate(legacy)
        assert config.tokenizer == "cl100k_base"
        assert config.auto_rename_outputs is True
        assert config.save_in_current_dir is True

    def test_dump_roundtrip_uses_new_names(self):
        data = PresetConfig(name="x").model_dump(mode="json")
        assert "tokenizer" in data
        assert "auto_rename_outputs" in data
        assert "save_in_current_dir" in data
        assert "encoding" not in data
        assert "use_numbering" not in data
