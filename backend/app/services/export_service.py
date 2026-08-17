"""Export service for CSV and JSON file generation."""

import csv
import io
import json
from typing import Any


def escape_csv_value(value: Any) -> str:
    """Escape a single CSV value according to RFC 4180."""
    if value is None:
        return ""
    string_value = str(value)
    # Wrap in quotes if contains comma, quote, or newline
    if (
        "," in string_value
        or '"' in string_value
        or "\n" in string_value
        or "\r" in string_value
    ):
        # Double up quotes inside the value
        return '"' + string_value.replace('"', '""') + '"'
    return string_value


def rows_to_csv(columns: list[dict[str, str]], rows: list[dict[str, Any]]) -> str:
    """
    Convert query result rows to CSV string.

    Args:
        columns: List of column definitions with 'name' key
        rows: List of row dictionaries

    Returns:
        RFC 4180-compliant CSV string
    """
    if not columns:
        return ""

    headers = [col["name"] for col in columns]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # Write BOM for Excel UTF-8 compatibility
    # Write header row
    writer.writerow(headers)

    # Write data rows
    for row in rows:
        values = [escape_csv_value(row.get(h)) for h in headers]
        writer.writerow(values)

    return output.getvalue()


def rows_to_json(
    columns: list[dict[str, str]], rows: list[dict[str, Any]], indent: int = 2
) -> str:
    """
    Convert query result rows to JSON string.

    Args:
        columns: List of column definitions (for potential schema)
        rows: List of row dictionaries
        indent: JSON indentation spaces

    Returns:
        JSON string
    """
    return json.dumps(rows, ensure_ascii=False, indent=indent, default=str)


def build_export_response(
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    export_format: str,
    filename: str | None,
    database_name: str,
) -> tuple[bytes, str, str]:
    """
    Build export file bytes and content-disposition header value.

    Args:
        columns: Query column definitions
        rows: Query result rows
        export_format: 'csv' or 'json'
        filename: Optional custom filename (without extension)
        database_name: Database name for default filename

    Returns:
        Tuple of (file_bytes, content_type, download_filename)
    """
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")

    if export_format == "csv":
        content = rows_to_csv(columns, rows)
        # Add UTF-8 BOM for Excel compatibility
        content_bytes = "\ufeff".encode("utf-8") + content.encode("utf-8")
        mime = "text/csv; charset=utf-8"
        fname = f"{filename or database_name}_{ts}.csv"
    else:  # json
        content = rows_to_json(columns, rows)
        content_bytes = content.encode("utf-8")
        mime = "application/json; charset=utf-8"
        fname = f"{filename or database_name}_{ts}.json"

    return content_bytes, mime, fname