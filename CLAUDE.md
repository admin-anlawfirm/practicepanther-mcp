# PracticePanther MCP Server

## PracticePanther API Documentation

- **Swagger Spec (JSON)**: `swagger-v2.json` in this repo (local copy of the spec below)
- **Swagger Spec (live)**: https://app.practicepanther.com/swagger/docs/v2
- **Swagger UI (interactive)**: https://app.practicepanther.com/swagger/ui/index
- **API Overview & OData Guide**: https://support.practicepanther.com/en/articles/479897-practicepanther-api
- **API Reference (models & endpoints)**: https://app.practicepanther.com/content/apidocs/index.html
- **API Help Center**: https://support.practicepanther.com/en/collections/340699-api

When in doubt about parameter names or types, check `swagger-v2.json` — it is the source of truth.

## Architecture

- `server.py` - FastMCP server with 80+ tools covering all PracticePanther API v2 endpoints
- `pp_client.py` - HTTP client, token management, OData query builder
- `mcp_oauth_provider.py` - MCP OAuth 2.0 provider linking to PP OAuth
- `oauth.py` - PP OAuth helpers (authorize URL, token exchange)

## OData Query Support

All list endpoints support OData query options via these parameters:
- `top` / `skip` - pagination (maps to `$top` / `$skip`)
- `odata_filter` - OData filter expressions (maps to `$filter`)
- `orderby` - sorting (maps to `$orderby`)

Examples:
- `$top=50&$skip=100` - get records 101-150
- `$filter=contains(user/name, 'john')` - filter by name substring
- `$orderby=date desc` - sort by date descending
- `$filter=status eq 'Open'` - filter by exact match

The `build_odata_params()` helper in `pp_client.py` merges regular filter params with OData system query options.

**Important**: OData `$filter` datetime values MUST include timezone info (e.g. `2026-04-06T00:00:00Z`). Without the `Z` or offset, the API returns a 400 error.

## Deployment

Deployed on Render free tier (512MB RAM). Uses Redis for token persistence with in-memory fallback.
