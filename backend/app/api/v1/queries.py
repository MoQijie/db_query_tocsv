"""Query execution API endpoints."""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import List

from app.database import get_session
from app.models.database import DatabaseConnection
from app.models.query import QuerySource
from app.models.schemas import (
    QueryInput,
    QueryResult,
    QueryHistoryEntry,
    NaturalLanguageInput,
    GeneratedSqlResponse,
    ExportQueryInput,
    ExportNLQueryInput,
)
from app.services.export_service import build_export_response
from app.services.query_wrapper import execute_query_with_service
from app.services.query import get_query_history
from app.services.sql_validator import SqlValidationError
from app.services.nl2sql import nl2sql_service
from app.services.metadata import get_cached_metadata

router = APIRouter(prefix="/api/v1/dbs", tags=["queries"])


def to_history_entry(history) -> QueryHistoryEntry:
    """Convert QueryHistory to QueryHistoryEntry schema."""
    return QueryHistoryEntry(
        id=history.id,
        databaseName=history.database_name,
        sqlText=history.sql_text,
        executedAt=history.executed_at,
        executionTimeMs=history.execution_time_ms,
        rowCount=history.row_count,
        success=history.success,
        errorMessage=history.error_message,
        querySource=history.query_source.value,
    )


@router.post("/{name}/query", response_model=QueryResult)
async def execute_sql_query(
    name: str,
    input_data: QueryInput,
    session: Session = Depends(get_session),
) -> QueryResult:
    """
    Execute SQL query against a database.

    Args:
        name: Database connection name
        input_data: Query input with SQL
        session: Database session

    Returns:
        Query result with columns and rows
    """
    # Get connection
    statement = select(DatabaseConnection).where(
        DatabaseConnection.name == name
    )
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    # Execute query
    try:
        result = await execute_query_with_service(
            session,
            name,
            connection.db_type,
            connection.url,
            input_data.sql,
            QuerySource.MANUAL,
        )
        return result
    except SqlValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )


@router.get("/{name}/history", response_model=List[QueryHistoryEntry])
async def get_query_history_for_database(
    name: str,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> List[QueryHistoryEntry]:
    """
    Get query history for a database.

    Args:
        name: Database connection name
        limit: Maximum number of queries to return
        session: Database session

    Returns:
        List of query history entries
    """
    # Verify connection exists
    statement = select(DatabaseConnection).where(
        DatabaseConnection.name == name
    )
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    # Get history
    history_list = await get_query_history(session, name, limit)
    return [to_history_entry(h) for h in history_list]


@router.post("/{name}/query/natural", response_model=GeneratedSqlResponse)
async def natural_language_to_sql(
    name: str,
    input_data: NaturalLanguageInput,
    session: Session = Depends(get_session),
) -> GeneratedSqlResponse:
    """
    Convert natural language to SQL query using OpenAI.

    Args:
        name: Database connection name
        input_data: Natural language prompt
        session: Database session

    Returns:
        Generated SQL query with explanation
    """
    # Get connection
    statement = select(DatabaseConnection).where(DatabaseConnection.name == name)
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    # Get metadata for context
    try:
        metadata_obj = await get_cached_metadata(session, connection.name)
        if not metadata_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata not found for database '{name}'. Please refresh metadata first.",
            )
        metadata = json.loads(metadata_obj.metadata_json)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load metadata: {str(e)}",
        )

    # Generate SQL
    try:
        result = await nl2sql_service.generate_sql(
            input_data.prompt, metadata, connection.db_type
        )
        return GeneratedSqlResponse(
            sql=result["sql"],
            explanation=result["explanation"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate SQL: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Export Endpoints
# ---------------------------------------------------------------------------


async def _run_export(
    name: str,
    sql: str,
    export_format: str,
    filename: str | None,
    session: Session,
) -> Response:
    """
    Shared logic for query + export endpoints.

    Returns a FastAPI Response with the file as binary content.
    """
    statement = select(DatabaseConnection).where(
        DatabaseConnection.name == name
    )
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    try:
        result = await execute_query_with_service(
            session,
            name,
            connection.db_type,
            connection.url,
            sql,
            QuerySource.MANUAL,
        )
    except SqlValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )

    columns = [{"name": c.name, "dataType": c.data_type} for c in result.columns]
    file_bytes, content_type, download_filename = build_export_response(
        columns=columns,
        rows=result.rows,
        export_format=export_format,
        filename=filename,
        database_name=name,
    )

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


@router.post("/{name}/query-export")
async def query_and_export(
    name: str,
    input_data: ExportQueryInput,
    session: Session = Depends(get_session),
) -> Response:
    """
    Execute a SQL query and export the result directly as a CSV or JSON file.

    This endpoint is ideal for automation scripts and CLI tools that need
    a one-step query + download workflow.

    Args:
        name: Database connection name
        input_data: ExportQueryInput with sql, format (csv|json), optional filename
        session: Database session

    Returns:
        Binary file download (CSV or JSON)
    """
    return await _run_export(
        name=name,
        sql=input_data.sql,
        export_format=input_data.format,
        filename=input_data.filename,
        session=session,
    )


@router.post("/{name}/query-export/natural")
async def nl_query_and_export(
    name: str,
    input_data: ExportNLQueryInput,
    session: Session = Depends(get_session),
) -> Response:
    """
    Convert a natural language prompt to SQL, execute it, and export the result.

    This is a fully automated one-step pipeline: natural language → SQL →
    execute → export. Ideal for AI-assistant-driven data exports.

    Args:
        name: Database connection name
        input_data: ExportNLQueryInput with prompt, format (csv|json), optional filename
        session: Database session

    Returns:
        Binary file download (CSV or JSON)
    """
    statement = select(DatabaseConnection).where(DatabaseConnection.name == name)
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    # Step 1: Get metadata for NL→SQL
    try:
        metadata_obj = await get_cached_metadata(session, connection.name)
        if not metadata_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata not found for '{name}'. Please refresh metadata first.",
            )
        metadata = json.loads(metadata_obj.metadata_json)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load metadata: {str(e)}",
        )

    # Step 2: Generate SQL from natural language
    try:
        result = await nl2sql_service.generate_sql(
            input_data.prompt, metadata, connection.db_type
        )
        generated_sql = result["sql"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate SQL: {str(e)}",
        )

    # Step 3: Execute and export
    return await _run_export(
        name=name,
        sql=generated_sql,
        export_format=input_data.format,
        filename=input_data.filename,
        session=session,
    )