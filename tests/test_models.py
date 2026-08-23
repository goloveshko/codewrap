"""Tests for configuration models, including backward compatibility (review #5)."""

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

    def test_dump_roundtrip_excludes_removed_fields(self):
        data = PresetConfig(name="x").model_dump(mode="json")
        assert "respect_gitignore" not in data
        assert "include_tree" not in data
