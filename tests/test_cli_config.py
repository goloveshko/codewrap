"""Tests for `codewrap config set` encoding validation (review #17)."""

import pytest
from typer.testing import CliRunner

from codewrap import cli
from codewrap.main import app
from codewrap.settings import AppSettings

runner = CliRunner()


class FakeSettingsManager:
    saved: AppSettings | None = None

    def load(self) -> AppSettings:
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        FakeSettingsManager.saved = settings


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch: pytest.MonkeyPatch):
    FakeSettingsManager.saved = None
    monkeypatch.setattr(cli, "SettingsManager", FakeSettingsManager)


@pytest.fixture
def fake_tiktoken(monkeypatch: pytest.MonkeyPatch):
    import tiktoken

    registry = {"o200k_base"}

    def get_encoding(name: str):
        if name not in registry:
            raise ValueError(f"Unknown encoding {name}")
        return object()

    monkeypatch.setattr(tiktoken, "get_encoding", get_encoding)
    return registry


def test_invalid_encoding_rejected(fake_tiktoken, capsys):
    result = runner.invoke(app, ["config", "set", "--encoding", "bogus-enc"])
    assert result.exit_code == 1
    assert FakeSettingsManager.saved is None
    assert "Unknown tokenizer encoding" in result.output


def test_valid_encoding_saved(fake_tiktoken):
    result = runner.invoke(app, ["config", "set", "--encoding", "o200k_base"])
    assert result.exit_code == 0
    assert FakeSettingsManager.saved is not None
    assert FakeSettingsManager.saved.encoding == "o200k_base"


def test_other_flags_still_work_without_encoding():
    result = runner.invoke(app, ["config", "set", "--numbered"])
    assert result.exit_code == 0
    assert FakeSettingsManager.saved is not None
    assert FakeSettingsManager.saved.use_numbering is True
