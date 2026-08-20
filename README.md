# Postgres MCP (Ascend fork)

A fork of [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) (Postgres MCP Pro). This README documents only the changes made in this fork — see the [upstream README](https://github.com/crystaldba/postgres-mcp#readme) for full documentation of the base server (index tuning, database health checks, query plan analysis, safe SQL execution, and client configuration).

## Changes in this fork

### Simplified schema exploration tools

The upstream `list_schemas`, `list_objects`, and `get_object_details` tools were replaced with two simpler tools:

- **`list_tables`** — lists all user tables in the database (system schemas `pg_catalog` and `information_schema` excluded), returning `schema` and `table` for each.
- **`get_table_schema`** — returns the column structure (name, data type, nullability) of a single table. Accepts a plain table name (defaults to the `public` schema) or a schema-qualified name like `sales.orders`.

All other upstream tools (`execute_sql`, `explain_query`, `analyze_db_health`, `get_top_queries`, index tuning tools, etc.) are unchanged.

### Bearer token authentication for HTTP transports

When exposing the server over an HTTP transport (`sse` or `streamable-http`), you can require a bearer token on every request using the `--bearer-token` option or the `MCP_BEARER_TOKEN` environment variable (the environment variable takes precedence):

```bash
docker run -p 8000:8000 \
  -e DATABASE_URI=postgresql://username:password@localhost:5432/dbname \
  -e MCP_BEARER_TOKEN=your-secret-token \
  danzz0024511/postgres-mcp --access-mode=unrestricted --transport=streamable-http --streamable-http-host=0.0.0.0
```

Requests without a valid `Authorization: Bearer your-secret-token` header receive a `401 Unauthorized` response.
Configure your MCP client to send the header, for example:

```json
{
    "mcpServers": {
        "postgres": {
            "type": "sse",
            "url": "http://localhost:8000/sse",
            "headers": {
                "Authorization": "Bearer your-secret-token"
            }
        }
    }
}
```

The token is ignored for the `stdio` transport, which does not use HTTP.

DNS rebinding protection is disabled in this fork's transport security settings so the HTTP transports can be reached via arbitrary hostnames (e.g., from inside Docker networks).

### Docker image

The image is published to Docker Hub as [`danzz0024511/postgres-mcp`](https://hub.docker.com/r/danzz0024511/postgres-mcp). The Dockerfile was simplified from upstream's multi-stage build to a single-stage `python:3.12-slim-bookworm` build using `uv`.

```bash
docker pull danzz0024511/postgres-mcp:latest
```

## License

Apache-2.0, same as upstream. See [LICENSE](LICENSE).
