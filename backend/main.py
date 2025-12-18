from __future__ import annotations

import logging
import os
from typing import Any, List

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import get_connection, get_query_timeout_seconds
from gemini_llm import GeminiError, generate_sql
from schema import DatabaseSchema, load_schema
from sql_guard import SqlValidationError, validate_and_normalize_sql


load_dotenv()


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


_configure_logging()
logger = logging.getLogger("db-chatbot")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")


class ChatResponse(BaseModel):
    question: str
    sql: str
    columns: List[str]
    rows: List[List[Any]]


class TablesResponse(BaseModel):
    tables: List[str]


class FullSchemaResponse(BaseModel):
    tables: list[dict[str, Any]]


app = FastAPI(title="SQLGenie", version="1.0.0")


cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    """Load DB schema once and keep it cached for all requests."""
    try:
        with get_connection() as conn:
            schema_obj = load_schema(conn)
        app.state.db_schema = schema_obj
        app.state.schema_prompt = schema_obj.to_prompt_string()
        logger.info("Loaded schema: %s tables", len(schema_obj.tables))
    except Exception:
        logger.exception("Failed to load schema on startup")
        raise


@app.get("/tables", response_model=TablesResponse)
def list_tables() -> TablesResponse:
    schema_obj: DatabaseSchema = app.state.db_schema
    names = [f"[{t.schema}].[{t.name}]" for t in schema_obj.tables]
    return TablesResponse(tables=names)


@app.get("/schema", response_model=FullSchemaResponse)
def get_schema() -> FullSchemaResponse:
    schema_obj: DatabaseSchema = app.state.db_schema
    return FullSchemaResponse(
        tables=[
            {
                "schema": t.schema,
                "name": t.name,
                "type": t.table_type,
                "columns": [
                    {
                        "name": c.name,
                        "data_type": c.data_type,
                        "is_nullable": c.is_nullable,
                        "max_length": c.max_length,
                        "precision": c.precision,
                        "scale": c.scale,
                    }
                    for c in t.columns
                ],
            }
            for t in schema_obj.tables
        ]
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    schema_prompt: str = app.state.schema_prompt

    try:
        sql_raw = generate_sql(req.question, schema_prompt=schema_prompt)
        sql = validate_and_normalize_sql(sql_raw)
    except (ValueError, SqlValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GeminiError as e:
        logger.exception("LLM failure")
        # Upstream LLM error (e.g. misconfigured model, auth, quota).
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("LLM failure")
        raise HTTPException(status_code=500, detail="LLM generation failed")

    try:
        with get_connection() as conn:
            cur = conn.cursor()

            # pyodbc timeout support varies by version/driver:
            # - Some expose cursor.timeout
            # - Others use connection.timeout
            timeout_s = get_query_timeout_seconds(30)
            try:
                cur.timeout = timeout_s  # type: ignore[attr-defined]
            except Exception:
                try:
                    conn.timeout = timeout_s  # type: ignore[attr-defined]
                except Exception:
                    pass

            cur.execute(sql)

            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(100) if cur.description else []
            # Convert pyodbc Row objects to JSON-serializable lists.
            out_rows: List[List[Any]] = [list(r) for r in rows]

        return ChatResponse(question=req.question, sql=sql, columns=columns, rows=out_rows)
    except pyodbc.Error as e:
        # Log the SQL to make debugging easier in local/dev.
        logger.exception("Database query failed. SQL was: %s", sql)
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    except Exception as e:
        logger.exception("Database query failed. SQL was: %s", sql)
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")


# Local dev entrypoint:
#   uvicorn main:app --reload --host 0.0.0.0 --port 8000
