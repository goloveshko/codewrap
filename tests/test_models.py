"""Tests for the ScanConfig model: defaults, nesting, and dump/validate roundtrip."""

from codewrap.models import ScanConfig, TargetRule


class TestScanConfig:
    def test_defaults(self):
        config = ScanConfig()
        assert config.tokenizer == "o200k_base"
        assert config.targets == []
        assert config.excludes == []
        assert config.copy_to_clipboard is False
        assert config.auto_rename_outputs is False
        assert config.save_in_current_dir is False

    def test_roundtrip_keeps_nested_target_rules(self):
        config = ScanConfig(
            root_path="proj",
            targets=[TargetRule(path="src", extensions=["py", "toml"])],
            excludes=["tests/**"],
        )
        data = config.model_dump(mode="json")
        assert data["targets"][0]["extensions"] == ["py", "toml"]
        assert ScanConfig.model_validate(data) == config
