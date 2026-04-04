---
name: generate-mcp-credentials
description: Generate or rotate MCP OAuth client credentials (MCP_CLIENT_ID and MCP_CLIENT_SECRET) for the PracticePanther MCP server. Use this skill whenever the user asks to generate credentials, rotate credentials, create a new client ID/secret, rotate MCP keys, reset connector auth, or set up the Claude connector for the first time.
---

# Generate MCP Credentials

Generate new MCP OAuth client credentials for the PracticePanther MCP server's Claude connector.

## What these credentials are

These are the **MCP server's own OAuth client credentials** — they authenticate the Claude connector as an authorized client of your MCP server. They are NOT PracticePanther API credentials.

- **MCP_CLIENT_ID**: Identifies the Claude connector to the MCP server
- **MCP_CLIENT_SECRET**: Proves the Claude connector is authorized to initiate OAuth flows

## Steps

### 1. Generate credentials

Run this command to generate cryptographically secure credentials:

```bash
python3 -c "import secrets; print('MCP_CLIENT_ID:', secrets.token_hex(16)); print('MCP_CLIENT_SECRET:', secrets.token_urlsafe(32))"
```

### 2. Update Render environment variables

Use the Render MCP tool to set the new values on the PracticePanther MCP service.

The Render service ID is `srv-d78353aa214c739vicm0`.

Use the `mcp__render__update_environment_variables` tool:
- `serviceId`: `srv-d78353aa214c739vicm0`
- `envVars`: set both `MCP_CLIENT_ID` and `MCP_CLIENT_SECRET` to the newly generated values

This triggers an automatic redeploy.

### 3. Instruct the user

After updating Render, tell the user:

1. **Update the Claude connector** — go to Claude.ai connector settings and enter the new Client ID and Client Secret
2. **Save credentials securely** — store the new MCP_CLIENT_ID and MCP_CLIENT_SECRET in a password manager (1Password, etc.). They are only visible in this conversation and in the Render dashboard.
3. **Old credentials are immediately invalid** — anyone using the old credentials will need the new ones

### Important notes

- Always generate BOTH values together. Never reuse an old ID with a new secret or vice versa.
- The credentials are set as Render env vars with `sync: false` so they are never committed to the repo.
- If rotating due to a suspected leak, rotate immediately and notify all team members to update their Claude connector settings.
