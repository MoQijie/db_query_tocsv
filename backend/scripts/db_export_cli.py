#!/usr/bin/env python3
"""
db_export_cli.py - Automated database query and export tool

Provides one-command data export with support for both raw SQL and natural language queries.
Supports CSV and JSON export formats.

Usage:
    python scripts/db_export_cli.py --db mydb --sql "SELECT * FROM users LIMIT 100" --format csv
    python scripts/db_export_cli.py --db mydb --sql "SELECT * FROM orders" --format json
    python scripts/db_export_cli.py --db mydb --prompt "查询所有最近30天的活跃用户" --format csv
    python scripts/db_export_cli.py --db mydb --prompt "Show all active users from last 30 days" --format json
    python scripts/db_export_cli.py --list-dbs
    python scripts/db_export_cli.py --help
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

DEFAULT_BASE_URL = os.environ.get("DB_QUERY_API_URL", "http://localhost:8000")
TIMEOUT = 60


def _get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db_export",
        description="Database query and export tool - supports SQL and natural language queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --db mydb --sql "SELECT * FROM users" --format csv
  %(prog)s --db mydb --sql "SELECT * FROM orders WHERE amount > 100" --format json --output mydata.json
  %(prog)s --db mydb --prompt "查找所有未完成的任务" --format csv
  %(prog)s --db mydb --prompt "Show all active users from last 30 days" --format json
  %(prog)s --list-dbs
        """,
    )
    parser.add_argument("--db", dest="database", metavar="NAME",
                        help="Database connection name (as registered in the app)")
    parser.add_argument("--sql", dest="sql", metavar="SQL",
                        help="SQL SELECT query to execute and export")
    parser.add_argument("--prompt", dest="prompt", metavar="TEXT",
                        help="Natural language query (AI will convert to SQL, then export)")
    parser.add_argument("--format", dest="format", choices=["csv", "json"],
                        default="csv", help="Export format (default: csv)")
    parser.add_argument("--output", dest="output", metavar="PATH",
                        help="Output file path. If omitted, auto-generates a filename.")
    parser.add_argument("--base-url", dest="base_url", default=DEFAULT_BASE_URL,
                        help=f"API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--list-dbs", dest="list_dbs", action="store_true",
                        help="List all registered database connections and exit")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress informational output")
    return parser


def _info(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"[db_export] {msg}", file=sys.stderr)


def _die(msg: str) -> None:
    print(f"[db_export] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _list_databases(base_url: str) -> list[dict]:
    try:
        resp = requests.get(f"{base_url}/api/v1/dbs", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        _die(f"Failed to list databases: {e}")


def _download_export(base_url: str, db_name: str, payload: dict) -> tuple[bytes, str]:
    endpoint = (
        f"{base_url}/api/v1/dbs/{db_name}/query-export/natural"
        if "prompt" in payload
        else f"{base_url}/api/v1/dbs/{db_name}/query-export"
    )
    try:
        resp = requests.post(endpoint, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Disposition", "")
    except requests.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                _die(f"API error: {e.response.json().get('detail', str(e))}")
            except Exception:
                pass
        _die(f"Export request failed: {e}")


def _extract_filename(header: str) -> str | None:
    m = re.search(r'filename="?([^";\n]+)"?', header)
    return m.group(1) if m else None


def _file_size(n: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> None:
    args = _get_parser().parse_args()

    if args.list_dbs:
        for db in _list_databases(args.base_url):
            print(
                f"{db.get('name', ''):<25} {db.get('dbType', ''):<12} "
                f"{db.get('status', ''):<10} {db.get('description', '')}"
            )
        return

    if not args.database:
        _die("--db <name> is required (use --list-dbs to see available databases)")
    if not args.sql and not args.prompt:
        _die("Either --sql <query> or --prompt <natural-language> is required")
    if args.sql and args.prompt:
        _die("Cannot use both --sql and --prompt at the same time")

    payload = (
        {"sql": args.sql, "format": args.format}
        if args.sql
        else {"prompt": args.prompt, "format": args.format}
    )
    mode = "SQL" if args.sql else "NL"
    desc = (args.sql or args.prompt)[:60] + "..."

    _info(f"[{mode}] Exporting '{args.database}' as {args.format.upper()} | {desc}", args.quiet)

    start = datetime.now()
    file_bytes, cd = _download_export(args.base_url, args.database, payload)
    elapsed = (datetime.now() - start).total_seconds()

    out_path = (
        Path(args.output)
        if args.output
        else Path.cwd() / (
            _extract_filename(cd)
            or f"{args.database}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{args.format}"
        )
    )
    out_path.write_bytes(file_bytes)
    _info(
        f"Saved {args.format.upper()} → {out_path} ({_file_size(len(file_bytes))}) in {elapsed:.1f}s",
        args.quiet,
    )

    if not args.quiet:
        try:
            text = file_bytes.decode("utf-8-sig")
            lines = text.strip().split("\n")
            preview = "\n".join(lines[:6])
            if len(lines) > 6:
                preview += f"\n... (+{len(lines) - 6} more rows)"
            print("\n--- Preview ---")
            print(preview)
        except Exception:
            pass


if __name__ == "__main__":
    main()