# PracticePanther MCP Server

MCP server providing full access to the PracticePanther legal practice management API (80+ tools covering all v2 endpoints).

## Tools

**Accounts**: list, get, create, update, delete
**Contacts**: list, get
**Matters**: list, get, create, update, delete
**Time Entries**: list, get, create, update, delete
**Expenses**: list, get, create, update, delete
**Expense Categories**: list, get, create, update, delete
**Flat Fees**: list, get, create, update, delete
**Invoices**: list, get, delete
**Payments**: list, get, delete
**Call Logs**: list, get, create, update, delete
**Events**: list, get, create, update, delete
**Notes**: list, get, create, update, delete
**Emails**: list, get, create, update, delete
**Messages**: list, create, update, delete
**Tasks**: list, get, create, update, delete
**Files**: list, get, download, update, delete
**Items**: list, get, create, update, delete
**Bank Accounts**: list, get, create, update, delete
**Relationships**: list, get, create, update, delete
**Custom Fields**: company, matter, contact, single
**Tags**: account, matter, activity
**Users**: current, single, list

## Setup

### 1. Get PracticePanther API Credentials

1. Request API access at PracticePanther
2. Create a test account for development
3. Note your `client_id` and `client_secret`

### 2. Deploy to Render (Free)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) and create a new **Web Service**
3. Connect your GitHub repo
4. Render auto-detects the Dockerfile
5. Set environment variables:
   - `PP_CLIENT_ID` = your client ID
   - `PP_CLIENT_SECRET` = your client secret
   - `PP_REDIRECT_URI` = `https://YOUR-APP.onrender.com/oauth/callback`
6. Deploy - you'll get a free `https://YOUR-APP.onrender.com` domain

### 3. Connect to Claude Code

```bash
claude mcp add practicepanther \
  --transport streamable-http \
  https://YOUR-APP.onrender.com/mcp
```

### 4. Connect to Claude Cowork

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "practicepanther": {
      "type": "streamable-http",
      "url": "https://YOUR-APP.onrender.com/mcp"
    }
  }
}
```

### 5. Authenticate

1. Ask Claude to call `get_auth_url`
2. Visit the URL in your browser
3. Authorize the app in PracticePanther
4. You'll be redirected back - the server stores your tokens automatically
5. All tools are now ready to use

## Local Development

```bash
# Install dependencies
pip install -e .

# Set env vars
export PP_CLIENT_ID=your_id
export PP_CLIENT_SECRET=your_secret
export PP_REDIRECT_URI=http://localhost:8000/oauth/callback

# Run
python server.py
```

Server runs on `http://localhost:8000`. Connect Claude Code:

```bash
claude mcp add practicepanther \
  --transport streamable-http \
  http://localhost:8000/mcp
```
