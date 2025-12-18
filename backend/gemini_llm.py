from __future__ import annotations

import os
from typing import Iterable, Optional

from google import genai
from google.genai import types


class GeminiError(RuntimeError):
    pass


# Lazily computed model name to avoid listing models on every request.
_CACHED_MODEL: Optional[str] = None

# Cache whether an explicitly configured GEMINI_MODEL is valid, so we don't call ListModels repeatedly.
_CONFIGURED_MODEL: Optional[str] = None
_CONFIGURED_MODEL_VALID: Optional[bool] = None


def _get_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env var GOOGLE_API_KEY")
    return genai.Client(api_key=api_key)


def _normalize_model_name(model: str) -> str:
    """Accepts either 'gemini-2.0-flash' or 'models/gemini-2.0-flash'."""
    m = (model or "").strip()
    if not m:
        return m
    # Leave full resource names intact.
    if m.startswith("models/") or m.startswith("tunedModels/"):
        return m
    # If caller passed something like 'publishers/.../models/...' don't touch it.
    if "/" in m:
        return m
    return f"models/{m}"


def _iter_generate_models(client: genai.Client) -> Iterable[str]:
    """Yield model resource names that support generateContent."""
    for m in client.models.list():
        name = getattr(m, "name", None)
        actions = getattr(m, "supported_actions", None) or []
        if name and "generateContent" in actions:
            yield str(name)


def _pick_default_model(available: list[str]) -> str:
    # Prefer stable/cheap 'flash' variants first.
    preferred = [
        # Prefer Flash-Lite to reduce cost/quotas for simple text generation.
        "models/gemini-2.5-flash-lite",
        "models/gemini-flash-lite-latest",
        "models/gemini-2.0-flash-lite",
        "models/gemini-2.0-flash-lite-001",
        # Then regular Flash.
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-001",
        "models/gemini-2.5-flash",
        # Then Pro.
        "models/gemini-pro-latest",
        "models/gemini-2.5-pro",
    ]

    avail_set = set(available)
    for cand in preferred:
        if cand in avail_set:
            return cand

    # Fall back to whatever the API says is available.
    return available[0]


def _resolve_model(client: genai.Client) -> str:
    global _CACHED_MODEL, _CONFIGURED_MODEL, _CONFIGURED_MODEL_VALID

    # If we've already validated a configured model, reuse that result.
    if _CONFIGURED_MODEL_VALID is True and _CONFIGURED_MODEL:
        return _CONFIGURED_MODEL
    if _CONFIGURED_MODEL_VALID is False and _CACHED_MODEL:
        return _CACHED_MODEL

    configured = os.getenv("GEMINI_MODEL")
    if configured and _CONFIGURED_MODEL_VALID is None:
        normalized = _normalize_model_name(configured)
        _CONFIGURED_MODEL = normalized

        # Only validate plain `models/...` names. For other resource formats, assume the caller knows.
        if normalized.startswith("models/"):
            available = list(_iter_generate_models(client))
            if available and normalized in set(available):
                _CONFIGURED_MODEL_VALID = True
                return normalized

            # If user configured an unavailable model (common when copy/pasting older examples),
            # fall back to a working default.
            _CONFIGURED_MODEL_VALID = False
            if not available:
                raise GeminiError(
                    "No Gemini models available for generateContent. "
                    "Call client.models.list() to inspect available models, or set GEMINI_MODEL explicitly."
                )
            _CACHED_MODEL = _pick_default_model(available)
            return _CACHED_MODEL

        _CONFIGURED_MODEL_VALID = True
        return normalized

    if _CACHED_MODEL:
        return _CACHED_MODEL

    available = list(_iter_generate_models(client))
    if not available:
        raise GeminiError(
            "No Gemini models available for generateContent. "
            "Call client.models.list() to inspect available models, or set GEMINI_MODEL explicitly."
        )

    _CACHED_MODEL = _pick_default_model(available)
    return _CACHED_MODEL


def generate_sql(question: str, schema_prompt: str) -> str:
    """Generate SQL Server SELECT-only query using Gemini.

    The model is instructed to return ONLY SQL (no markdown, no explanation).
    """
    if not question or not question.strip():
        raise ValueError("Question is required")

    system_instruction = """
You are a senior data analyst writing Microsoft SQL Server queries.

RULES (MUST FOLLOW):
- Use ONLY the tables and columns present in the provided DATABASE SCHEMA.
- If the question cannot be answered with the schema, output exactly: SELECT 'Unable to answer with provided schema' AS error;
- Generate ONLY ONE SQL statement.
- ONLY SELECT queries are allowed.
- NEVER use: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, MERGE, CREATE, GRANT, REVOKE, EXEC, EXECUTE.
- Do NOT use comments, markdown, or code fences.
- Always limit results to TOP (100). If the question implies fewer rows, you may still use TOP (100).
- Use SQL Server compatible syntax.
- Prefer explicit schema qualification like [dbo].[TableName] when possible.
- Use bracket quoting for identifiers: [schema].[table], [column].
- Return ONLY the SQL text.
""".strip()

    prompt = f"""
DATABASE SCHEMA:
{schema_prompt}

USER QUESTION:
{question.strip()}

Return ONLY SQL Server SQL.
""".strip()

    client = _get_client()
    model = _resolve_model(client)

    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
                top_p=0.1,
                max_output_tokens=512,
                response_mime_type="text/plain",
            ),
        )
    except Exception as e:
        # Most common failure we saw: misconfigured/unsupported model name (404 NOT_FOUND).
        raise GeminiError(
            f"Gemini generateContent failed using model '{model}'. "
            "Set GEMINI_MODEL to a valid model from client.models.list()."
        ) from e

    sql = (resp.text or "").strip()
    if not sql:
        raise GeminiError("Gemini returned an empty response")
    return sql
