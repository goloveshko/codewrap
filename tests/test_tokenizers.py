"""Tests for tokenizer/model alias resolution and honest token counting."""

import pytest

from codewrap.engine import CodeProcessorEngine
from codewrap.models import ScanConfig
from codewrap.tokenizers import encoding_models, resolve_tokenizer


class TestResolveTokenizer:
    def test_model_aliases_map_to_encodings(self):
        assert resolve_tokenizer("Claude") == "cl100k_base"
        assert resolve_tokenizer("gpt-4o") == "o200k_base"
        assert resolve_tokenizer("  GPT-4 ") == "cl100k_base"

    def test_encoding_names_pass_through(self):
        assert resolve_tokenizer("cl100k_base") == "cl100k_base"
        assert resolve_tokenizer("p50k_base") == "p50k_base"

    def test_unknown_values_pass_through_for_engine_validation(self):
        assert resolve_tokenizer("bogus") == "bogus"

    def test_encoding_models_descriptions(self):
        assert "Claude" in encoding_models("cl100k_base")
        assert encoding_models("weird").startswith("custom")


def make_engine(root, tokenizer="dummy-tokenizer-for-tests"):
    config = ScanConfig(root_path=str(root), tokenizer=tokenizer)
    return CodeProcessorEngine(config, exclude_binary=False)


class TestEstimateReporting:
    def test_broken_tokenizer_marks_estimate_reason(self, tmp_path):
        engine = make_engine(tmp_path)
        assert engine.tokenizer is None
        assert engine.estimate_reason and "dummy-tokenizer" in engine.estimate_reason

    def test_working_tokenizer_reports_no_estimate(self, tmp_path):
        try:
            import tiktoken

            tiktoken.get_encoding("o200k_base")
        except Exception:
            pytest.skip("tiktoken encoding not available offline")
        engine = make_engine(tmp_path, tokenizer="o200k_base")
        assert engine.estimate_reason is None


class TestDocumentLevelCount:
    def test_total_counts_final_document_not_section_sum(self, tmp_path):
        engine = make_engine(tmp_path)
        (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
        files, total = engine.process()
        assert files == 1
        # Rough estimate path: total must cover headers/fences, not just content.
        content_only = engine.count_tokens("print(1)\n")
        assert total > content_only
        assert [p.name for p, *_ in engine.file_stats] == ["a.py"]
