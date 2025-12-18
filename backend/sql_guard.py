from __future__ import annotations

import re


_FORBIDDEN_TOKENS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "merge",
    "create",
    "grant",
    "revoke",
    "execute",
    "exec",
    "xp_",
    "sp_",
    "openrowset",
    "opendatasource",
}


class SqlValidationError(ValueError):
    pass


def validate_and_normalize_sql(sql: str) -> str:
    """Validates that SQL is a single, safe SELECT statement and enforces TOP 100.

    Returns a normalized SQL string that is safe to execute.
    """
    if not sql or not sql.strip():
        raise SqlValidationError("Empty SQL")

    cleaned = _strip_code_fences(sql).strip()

    # Reject SQL comments to reduce prompt-injection and multi-statement tricks.
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SqlValidationError("SQL comments are not allowed")

    # Disallow multiple statements. Allow a single trailing semicolon only.
    semi_count = cleaned.count(";")
    if semi_count > 1:
        raise SqlValidationError("Multiple statements are not allowed")
    if semi_count == 1 and not cleaned.rstrip().endswith(";"):
        raise SqlValidationError("Semicolons are only allowed at the end")
    cleaned = cleaned.rstrip().rstrip(";").strip()

    # Must start with SELECT (WITH is allowed if it leads into SELECT), but for safety we disallow WITH
    # because it complicates validation and can be used to stage data. Keep it strict.
    if re.match(r"^\s*with\b", cleaned, flags=re.IGNORECASE):
        raise SqlValidationError("CTEs (WITH ...) are not allowed")

    if not re.match(r"^\s*select\b", cleaned, flags=re.IGNORECASE):
        raise SqlValidationError("Only SELECT statements are allowed")

    lowered = cleaned.lower()
    for tok in _FORBIDDEN_TOKENS:
        if tok in lowered:
            raise SqlValidationError(f"Forbidden token detected: {tok}")

    # Normalize a common model failure: duplicate TOP right after SELECT.
    # Example: SELECT TOP (100) TOP (100) '...' -> SELECT TOP (100) '...'
    cleaned = _collapse_duplicate_leading_top(cleaned)

    # Reject TOP used anywhere other than immediately after SELECT[/DISTINCT].
    # The model sometimes emits invalid SQL like: SELECT col, TOP (10) ... which SQL Server rejects.
    prefix = re.match(
        r"^\s*select\s+(distinct\s+)?(top\s*\(\s*\d+\s*\)|top\s+\d+)?\s*",
        cleaned,
        flags=re.IGNORECASE,
    )
    if prefix:
        rest = cleaned[prefix.end() :]
        if re.search(r"\btop\b", rest, flags=re.IGNORECASE):
            raise SqlValidationError("TOP is only allowed immediately after SELECT")

    # Enforce TOP 100 (and cap any TOP to <= 100).
    cleaned = _enforce_top_100(cleaned)

    # Final normalization pass: if the model produced duplicate TOPs and we somehow missed it,
    # collapse them so SQL Server doesn't error.
    cleaned = _collapse_duplicate_leading_top(cleaned)

    # Basic sanity: must contain FROM (unless it's a simple scalar select; allow those).
    # This helps reduce "SELECT 1" returning nonsense; still allowed.
    return cleaned


def _strip_code_fences(text: str) -> str:
    """Removes Markdown-style ``` fences if the model returns them."""
    t = text.strip()
    if t.startswith("```"):
        # Remove first line fence and last fence.
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t


def _collapse_duplicate_leading_top(sql: str) -> str:
    """Remove duplicated TOP clauses immediately after SELECT[/DISTINCT].

    The model sometimes emits: SELECT TOP (100) TOP (100) ... which SQL Server rejects.
    We keep the first TOP and drop subsequent consecutive TOPs.
    """
    m = re.match(r"^\s*select\s+(distinct\s+)?", sql, flags=re.IGNORECASE)
    if not m:
        return sql

    prefix_end = m.end()
    after_select = sql[prefix_end:]

    # NOTE: don't use \b after ")" because it's not a word boundary.
    top_re = re.compile(r"^(top\s*\(\s*\d+\s*\)|top\s+\d+)(?:\s+|$)", flags=re.IGNORECASE)
    first = top_re.match(after_select)
    if not first:
        return sql

    kept_top = first.group(0).strip()  # preserve the first TOP clause
    rest = after_select[first.end() :].lstrip()

    # Drop any additional consecutive TOP clauses.
    while True:
        nxt = top_re.match(rest)
        if not nxt:
            break
        rest = rest[nxt.end() :].lstrip()

    return sql[:prefix_end] + kept_top + " " + rest


def _enforce_top_100(sql: str) -> str:
    # If the model duplicated TOP, strip the duplicates first so we can safely cap/insert.
    sql = _collapse_duplicate_leading_top(sql)

    # Case-insensitive match for SELECT [DISTINCT]
    m = re.match(r"^\s*select\s+(distinct\s+)?", sql, flags=re.IGNORECASE)
    if not m:
        raise SqlValidationError("Only SELECT statements are allowed")

    prefix_end = m.end()
    after_select = sql[prefix_end:]

    # If TOP exists right after SELECT/DISTINCT, cap it.
    # NOTE: don't use \b after ")" because it's not a word boundary.
    top_match = re.match(
        r"^(top\s*\(\s*(\d+)\s*\)|top\s+(\d+))(?:\s+|$)",
        after_select,
        flags=re.IGNORECASE,
    )
    if top_match:
        n = top_match.group(2) or top_match.group(3)
        try:
            n_int = int(n)
        except Exception:
            n_int = 100
        capped = min(max(n_int, 1), 100)
        # Replace original TOP... with TOP (capped)
        rest = after_select[top_match.end() :]
        return sql[:prefix_end] + f"TOP ({capped}) " + rest.lstrip()

    # Otherwise inject TOP (100) right after SELECT/DISTINCT.
    return sql[:prefix_end] + "TOP (100) " + after_select.lstrip()
