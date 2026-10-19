import ast
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from postgres_mcp.server import check_allowed_values
from postgres_mcp.server import get_table_schema
from postgres_mcp.server import list_tables
from postgres_mcp.sql.sql_driver import SqlDriver


def rows(*cells):
    return [SqlDriver.RowResult(cells=c) for c in cells]


def column(name, data_type, nullable="YES", comment=None, table_comment=None, relkind="r"):
    return {
        "column_name": name,
        "data_type": data_type,
        "is_nullable": nullable,
        "column_comment": comment,
        "table_comment": table_comment,
        "relkind": relkind,
    }


def key(kind, columns, ref_table=None, ref_columns=None, definition=None):
    return {"kind": kind, "columns": columns, "ref_table": ref_table, "ref_columns": ref_columns or [], "definition": definition}


async def call_schema(table, results):
    driver = MagicMock()
    driver.execute_query = AsyncMock(side_effect=results)
    with patch("postgres_mcp.server.get_sql_driver", AsyncMock(return_value=driver)):
        response = await get_table_schema(table)
    return response[0].text, driver


@pytest.mark.parametrize(
    "definition,expected",
    [
        ("CHECK ((answer = ANY (ARRAY['comply'::text, 'not_comply'::text, 'na'::text])))", ["comply", "not_comply", "na"]),
        ("CHECK ((status = 'approved'::text))", ["approved"]),
        (
            "CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying])::text[])))",
            ["open", "closed"],
        ),
        ("CHECK ((\"Status\" = ANY (ARRAY['a'::text, 'b''s'::text])))", ["a", "b's"]),
        ("CHECK (((facility_id IS NULL) = (facility_match IS NULL)))", None),
        ("CHECK (((a = ANY (ARRAY['x'::text])) AND (b = ANY (ARRAY['y'::text]))))", None),
        ("CHECK ((level = ANY (ARRAY[1, 2, 3])))", None),
        ("CHECK ((price > (0)::numeric))", None),
    ],
)
def test_check_allowed_values(definition, expected):
    assert check_allowed_values(definition) == expected


@pytest.mark.asyncio
async def test_get_table_schema_shows_comments_keys_and_allowed_values():
    text, driver = await call_schema(
        "inspection_answer",
        [
            rows(
                column("submission_id", "text", "NO", table_comment="One row = one answer."),
                column("answer", "text", "NO", comment="comply | not_comply | na", table_comment="One row = one answer."),
                column("evidence_files", "text[]", table_comment="One row = one answer."),
            ),
            rows(
                key("p", ["submission_id", "answer"]),
                key("f", ["submission_id"], "inspection_visit", ["submission_id"], "FOREIGN KEY ..."),
                key("c", ["answer"], definition="CHECK ((answer = ANY (ARRAY['comply'::text, 'not_comply'::text, 'na'::text])))"),
                key("c", ["submission_id", "answer"], definition="CHECK ((submission_id <> answer))"),
            ),
        ],
    )
    assert ast.literal_eval(text) == {
        "schema": "public",
        "table": "inspection_answer",
        "comment": "One row = one answer.",
        "columns": [
            {"name": "submission_id", "type": "text", "nullable": "NO"},
            {
                "name": "answer",
                "type": "text",
                "nullable": "NO",
                "comment": "comply | not_comply | na",
                "allowed_values": ["comply", "not_comply", "na"],
            },
            {"name": "evidence_files", "type": "text[]", "nullable": "YES"},
        ],
        "primary_key": ["submission_id", "answer"],
        "foreign_keys": [{"columns": ["submission_id"], "references": "inspection_visit(submission_id)"}],
        "checks": ["CHECK ((submission_id <> answer))"],
    }
    assert driver.execute_query.await_args_list[0].args[1] == ["public", "inspection_answer"]


@pytest.mark.asyncio
async def test_get_table_schema_materialized_view_with_unique_index():
    text, driver = await call_schema(
        "reports.facility_scorecard",
        [
            rows(column("facility_id", "integer", relkind="m"), column("visits", "bigint", comment="Inspection visits.", relkind="m")),
            rows(key("u", ["facility_id"])),
        ],
    )
    result = ast.literal_eval(text)
    assert result["schema"] == "reports"
    assert result["kind"] == "materialized view"
    assert "comment" not in result
    assert result["unique"] == [["facility_id"]]
    assert driver.execute_query.await_args_list[1].args[1] == ["reports", "facility_scorecard"]


@pytest.mark.asyncio
async def test_get_table_schema_without_keys_or_comments_keeps_the_plain_shape():
    text, _ = await call_schema("private_facilities", [rows(column("site", "text")), []])
    assert ast.literal_eval(text) == {
        "schema": "public",
        "table": "private_facilities",
        "columns": [{"name": "site", "type": "text", "nullable": "YES"}],
    }


@pytest.mark.asyncio
async def test_get_table_schema_not_found():
    text, driver = await call_schema("missing", [[]])
    assert text == "Error: Table 'missing' not found in schema 'public'"
    assert driver.execute_query.await_count == 1


@pytest.mark.asyncio
async def test_list_tables_includes_materialized_views():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=rows({"table_schema": "public", "table_name": "facility_scorecard"}))
    with patch("postgres_mcp.server.get_sql_driver", AsyncMock(return_value=driver)):
        response = await list_tables()
    assert ast.literal_eval(response[0].text) == [{"schema": "public", "table": "facility_scorecard"}]
    assert "relkind = 'm'" in driver.execute_query.await_args.args[0]
