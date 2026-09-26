"""Tokenizer and model alias resolution for token counting.

tiktoken only ships OpenAI encodings; for other vendors we pick the closest
approximation (as repomix does): cl100k_base tracks Claude tokenization closely
enough for context-budget planning.
"""

ENCODING_MODELS = {
    "o200k_base": "GPT-4o, GPT-4o mini, o1, o3",
    "cl100k_base": "GPT-4, GPT-3.5, Claude (approximation)",
}

MODEL_ALIASES = {
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "o1": "o200k_base",
    "o3": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-3.5": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "claude": "cl100k_base",
    "claude-3": "cl100k_base",
    "claude-3.5": "cl100k_base",
    "claude-4": "cl100k_base",
    "claude-5": "cl100k_base",
}


def resolve_tokenizer(value: str) -> str:
    """Map a model name (e.g. 'claude') to a tiktoken encoding; pass real encoding names through."""
    v = value.strip().lower()
    return MODEL_ALIASES.get(v, v)


def encoding_models(encoding: str) -> str:
    """Human-readable description of which models an encoding approximates."""
    return ENCODING_MODELS.get(encoding, "custom encoding")
