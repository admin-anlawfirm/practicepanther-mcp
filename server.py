"""PracticePanther MCP Server - Full API coverage."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from oauth import exchange_code_for_tokens, get_authorize_url
from pp_client import api_delete, api_get, api_post, api_put, api_request

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "PracticePanther",
    instructions=(
        "MCP server for PracticePanther legal practice management. "
        "Call get_auth_url first to authenticate, then use any tool. "
        "All IDs are UUIDs. Dates are ISO 8601 UTC."
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["practicepanther-mcp.onrender.com", "localhost", "127.0.0.1"],
    ),
)

# ===========================================================================
# OAuth Tools
# ===========================================================================


@mcp.tool()
async def get_auth_url() -> str:
    """Get the PracticePanther OAuth authorization URL. User must visit this URL to grant access."""
    return get_authorize_url()


@mcp.tool()
async def check_auth_status() -> dict:
    """Check if the server currently has valid PracticePanther credentials."""
    from pp_client import token_store

    return {
        "authenticated": token_store.is_authenticated,
        "expired": token_store.is_expired if token_store.is_authenticated else None,
    }


# ===========================================================================
# Accounts (Clients/Companies)
# ===========================================================================


@mcp.tool()
async def list_accounts(
    assigned_to_user_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    search_text: Optional[str] = None,
    account_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther accounts (clients/companies). Filter by assignment, dates, search text, or tags."""
    return await api_get(
        "accounts",
        assigned_to_user_id=assigned_to_user_id,
        created_since=created_since,
        updated_since=updated_since,
        search_text=search_text,
        account_tag=account_tag,
    )


@mcp.tool()
async def get_account(id: str) -> Any:
    """Get a single PracticePanther account by ID."""
    return await api_get(f"accounts/{id}")


@mcp.tool()
async def create_account(account: dict) -> Any:
    """Create a new PracticePanther account. Provide fields like display_name, company_name, street_1, city, state, zip_code, notes, etc."""
    return await api_post("accounts", account)


@mcp.tool()
async def update_account(id: str, account: dict) -> Any:
    """Update an existing PracticePanther account. Provide the account ID and fields to update."""
    return await api_put("accounts", id, account)


@mcp.tool()
async def delete_account(id: str) -> Any:
    """Delete a PracticePanther account by ID."""
    return await api_delete("accounts", id)


# ===========================================================================
# Contacts
# ===========================================================================


@mcp.tool()
async def list_contacts(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    search_text: Optional[str] = None,
    account_tag: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Any:
    """List PracticePanther contacts. Filter by account, status (Active/Archived), search text, etc."""
    return await api_get(
        "contacts",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        status=status,
        created_since=created_since,
        updated_since=updated_since,
        search_text=search_text,
        account_tag=account_tag,
        company_name=company_name,
    )


@mcp.tool()
async def get_contact(id: str) -> Any:
    """Get a single PracticePanther contact by ID."""
    return await api_get(f"contacts/{id}")


# ===========================================================================
# Matters (Cases/Projects)
# ===========================================================================


@mcp.tool()
async def list_matters(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    search_text: Optional[str] = None,
    account_tag: Optional[str] = None,
    matter_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther matters. Filter by account, status (Open/Closed/Pending/Archived), tags, etc."""
    return await api_get(
        "matters",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        status=status,
        created_since=created_since,
        updated_since=updated_since,
        search_text=search_text,
        account_tag=account_tag,
        matter_tag=matter_tag,
    )


@mcp.tool()
async def get_matter(id: str) -> Any:
    """Get a single PracticePanther matter by ID."""
    return await api_get(f"matters/{id}")


@mcp.tool()
async def create_matter(matter: dict) -> Any:
    """Create a new PracticePanther matter. Provide account_ref, name, status, open_date, tags, etc."""
    return await api_post("matters", matter)


@mcp.tool()
async def update_matter(id: str, matter: dict) -> Any:
    """Update an existing PracticePanther matter."""
    return await api_put("matters", id, matter)


@mcp.tool()
async def delete_matter(id: str) -> Any:
    """Delete a PracticePanther matter by ID."""
    return await api_delete("matters", id)


# ===========================================================================
# Time Entries
# ===========================================================================


@mcp.tool()
async def list_time_entries(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    billed_by_user_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Any:
    """List PracticePanther time entries. Filter by account, matter, user, and date range."""
    return await api_get(
        "timeentries",
        account_id=account_id,
        matter_id=matter_id,
        billed_by_user_id=billed_by_user_id,
        created_since=created_since,
        updated_since=updated_since,
        date_from=date_from,
        date_to=date_to,
    )


@mcp.tool()
async def get_time_entry(id: str) -> Any:
    """Get a single PracticePanther time entry by ID."""
    return await api_get(f"timeentries/{id}")


@mcp.tool()
async def create_time_entry(time_entry: dict) -> Any:
    """Create a new PracticePanther time entry. Provide matter_ref, date, duration, description, rate, etc."""
    return await api_post("timeentries", time_entry)


@mcp.tool()
async def update_time_entry(id: str, time_entry: dict) -> Any:
    """Update an existing PracticePanther time entry."""
    return await api_put("timeentries", id, time_entry)


@mcp.tool()
async def delete_time_entry(id: str) -> Any:
    """Delete a PracticePanther time entry by ID."""
    return await api_delete("timeentries", id)


# ===========================================================================
# Expenses
# ===========================================================================


@mcp.tool()
async def list_expenses(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    billed_by_user_id: Optional[str] = None,
    expense_category_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Any:
    """List PracticePanther expenses. Filter by account, matter, user, category, and date range."""
    return await api_get(
        "Expenses",
        account_id=account_id,
        matter_id=matter_id,
        billed_by_user_id=billed_by_user_id,
        expense_category_id=expense_category_id,
        created_since=created_since,
        updated_since=updated_since,
        date_from=date_from,
        date_to=date_to,
    )


@mcp.tool()
async def get_expense(id: str) -> Any:
    """Get a single PracticePanther expense by ID."""
    return await api_get(f"Expenses/{id}")


@mcp.tool()
async def create_expense(expense: dict) -> Any:
    """Create a new PracticePanther expense. Provide matter_ref, date, qty, price, description, expense_category_ref, etc."""
    return await api_post("Expenses", expense)


@mcp.tool()
async def update_expense(id: str, expense: dict) -> Any:
    """Update an existing PracticePanther expense."""
    return await api_put("Expenses", id, expense)


@mcp.tool()
async def delete_expense(id: str) -> Any:
    """Delete a PracticePanther expense by ID."""
    return await api_delete("Expenses", id)


# ===========================================================================
# Expense Categories
# ===========================================================================


@mcp.tool()
async def list_expense_categories(
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther expense categories."""
    return await api_get(
        "ExpenseCategories",
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_expense_category(id: str) -> Any:
    """Get a single PracticePanther expense category by ID."""
    return await api_get(f"ExpenseCategories/{id}")


@mcp.tool()
async def create_expense_category(category: dict) -> Any:
    """Create a new PracticePanther expense category."""
    return await api_post("ExpenseCategories", category)


@mcp.tool()
async def update_expense_category(id: str, category: dict) -> Any:
    """Update an existing PracticePanther expense category."""
    return await api_put("ExpenseCategories", id, category)


@mcp.tool()
async def delete_expense_category(id: str) -> Any:
    """Delete a PracticePanther expense category by ID."""
    return await api_delete("ExpenseCategories", id)


# ===========================================================================
# Flat Fees
# ===========================================================================


@mcp.tool()
async def list_flat_fees(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    user_id: Optional[str] = None,
    item_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Any:
    """List PracticePanther flat fees. Filter by account, matter, user, item, and date range."""
    return await api_get(
        "flatfees",
        account_id=account_id,
        matter_id=matter_id,
        user_id=user_id,
        item_id=item_id,
        date_from=date_from,
        date_to=date_to,
    )


@mcp.tool()
async def get_flat_fee(id: str) -> Any:
    """Get a single PracticePanther flat fee by ID."""
    return await api_get(f"flatfees/{id}")


@mcp.tool()
async def create_flat_fee(flat_fee: dict) -> Any:
    """Create a new PracticePanther flat fee."""
    return await api_post("flatfees", flat_fee)


@mcp.tool()
async def update_flat_fee(id: str, flat_fee: dict) -> Any:
    """Update an existing PracticePanther flat fee."""
    return await api_put("flatfees", id, flat_fee)


@mcp.tool()
async def delete_flat_fee(id: str) -> Any:
    """Delete a PracticePanther flat fee by ID."""
    return await api_delete("flatfees", id)


# ===========================================================================
# Invoices (read + delete only)
# ===========================================================================


@mcp.tool()
async def list_invoices(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    top: Optional[int] = None,
    skip: Optional[int] = None,
) -> Any:
    """List PracticePanther invoices. Supports pagination with top/skip (max 2500 per request)."""
    params: dict[str, Any] = {}
    if account_id:
        params["account_id"] = account_id
    if matter_id:
        params["matter_id"] = matter_id
    if created_since:
        params["created_since"] = created_since
    if updated_since:
        params["updated_since"] = updated_since
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if top is not None:
        params["$top"] = top
    if skip is not None:
        params["$skip"] = skip
    return await api_request("GET", "invoices", params=params if params else None)


@mcp.tool()
async def get_invoice(id: str) -> Any:
    """Get a single PracticePanther invoice by ID."""
    return await api_get(f"invoices/{id}")


@mcp.tool()
async def delete_invoice(id: str) -> Any:
    """Delete a PracticePanther invoice by ID."""
    return await api_delete("invoices", id)


# ===========================================================================
# Payments (read + delete only)
# ===========================================================================


@mcp.tool()
async def list_payments(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther payments."""
    return await api_get(
        "payments",
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_payment(id: str) -> Any:
    """Get a single PracticePanther payment by ID."""
    return await api_get(f"payments/{id}")


@mcp.tool()
async def delete_payment(id: str) -> Any:
    """Delete a PracticePanther payment by ID."""
    return await api_delete("payments", id)


# ===========================================================================
# Call Logs
# ===========================================================================


@mcp.tool()
async def list_call_logs(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther call logs."""
    return await api_get(
        "calllogs",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
        date_from=date_from,
        date_to=date_to,
        activity_tag=activity_tag,
    )


@mcp.tool()
async def get_call_log(id: str) -> Any:
    """Get a single PracticePanther call log by ID."""
    return await api_get(f"calllogs/{id}")


@mcp.tool()
async def create_call_log(call_log: dict) -> Any:
    """Create a new PracticePanther call log. Provide matter_ref, date, duration, description, etc."""
    return await api_post("calllogs", call_log)


@mcp.tool()
async def update_call_log(id: str, call_log: dict) -> Any:
    """Update an existing PracticePanther call log."""
    return await api_put("calllogs", id, call_log)


@mcp.tool()
async def delete_call_log(id: str) -> Any:
    """Delete a PracticePanther call log by ID."""
    return await api_delete("calllogs", id)


# ===========================================================================
# Events
# ===========================================================================


@mcp.tool()
async def list_events(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther events."""
    return await api_get(
        "events",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
        date_from=date_from,
        date_to=date_to,
        activity_tag=activity_tag,
    )


@mcp.tool()
async def get_event(id: str) -> Any:
    """Get a single PracticePanther event by ID."""
    return await api_get(f"events/{id}")


@mcp.tool()
async def create_event(event: dict) -> Any:
    """Create a new PracticePanther event. Provide matter_ref, start_date, end_date, subject, description, etc."""
    return await api_post("events", event)


@mcp.tool()
async def update_event(id: str, event: dict) -> Any:
    """Update an existing PracticePanther event."""
    return await api_put("events", id, event)


@mcp.tool()
async def delete_event(id: str) -> Any:
    """Delete a PracticePanther event by ID."""
    return await api_delete("events", id)


# ===========================================================================
# Notes
# ===========================================================================


@mcp.tool()
async def list_notes(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther notes."""
    return await api_get(
        "notes",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
        activity_tag=activity_tag,
    )


@mcp.tool()
async def get_note(id: str) -> Any:
    """Get a single PracticePanther note by ID."""
    return await api_get(f"notes/{id}")


@mcp.tool()
async def create_note(note: dict) -> Any:
    """Create a new PracticePanther note. Provide matter_ref, subject, description, etc."""
    return await api_post("notes", note)


@mcp.tool()
async def update_note(id: str, note: dict) -> Any:
    """Update an existing PracticePanther note."""
    return await api_put("notes", id, note)


@mcp.tool()
async def delete_note(id: str) -> Any:
    """Delete a PracticePanther note by ID."""
    return await api_delete("notes", id)


# ===========================================================================
# Emails
# ===========================================================================


@mcp.tool()
async def list_emails(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
    external_message_id: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> Any:
    """List PracticePanther emails."""
    return await api_get(
        "emails",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
        external_message_id=external_message_id,
        activity_tag=activity_tag,
    )


@mcp.tool()
async def get_email(id: str) -> Any:
    """Get a single PracticePanther email by ID."""
    return await api_get(f"emails/{id}")


@mcp.tool()
async def create_email(email: dict) -> Any:
    """Create a new PracticePanther email record. Provide matter_ref, subject, body, from, to, etc."""
    return await api_post("emails", email)


@mcp.tool()
async def update_email(id: str, email: dict) -> Any:
    """Update an existing PracticePanther email record."""
    return await api_put("emails", id, email)


@mcp.tool()
async def delete_email(id: str) -> Any:
    """Delete a PracticePanther email by ID."""
    return await api_delete("emails", id)


# ===========================================================================
# Messages
# ===========================================================================


@mcp.tool()
async def list_messages(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    contact_id: Optional[str] = None,
) -> Any:
    """List PracticePanther messages (SMS/text)."""
    return await api_get(
        "messages",
        account_id=account_id,
        matter_id=matter_id,
        contact_id=contact_id,
    )


@mcp.tool()
async def create_message(message: dict) -> Any:
    """Create a new PracticePanther message. Provide contact_id, type, matter_id, subject, body, etc."""
    return await api_post("messages", message)


@mcp.tool()
async def update_message(message: dict) -> Any:
    """Update an existing PracticePanther message. Include the id in the message dict."""
    return await api_request("PUT", "messages", json_body=message)


@mcp.tool()
async def delete_message(id: str) -> Any:
    """Delete a PracticePanther message by ID."""
    return await api_delete("messages", id)


# ===========================================================================
# Tasks
# ===========================================================================


@mcp.tool()
async def list_tasks(
    assigned_to_user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther tasks."""
    return await api_get(
        "tasks",
        assigned_to_user_id=assigned_to_user_id,
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_task(id: str) -> Any:
    """Get a single PracticePanther task by ID."""
    return await api_get(f"tasks/{id}")


@mcp.tool()
async def create_task(task: dict) -> Any:
    """Create a new PracticePanther task. Provide matter_ref, subject, due_date, assigned_to, etc."""
    return await api_post("tasks", task)


@mcp.tool()
async def update_task(id: str, task: dict) -> Any:
    """Update an existing PracticePanther task."""
    return await api_put("tasks", id, task)


@mcp.tool()
async def delete_task(id: str) -> Any:
    """Delete a PracticePanther task by ID."""
    return await api_delete("tasks", id)


# ===========================================================================
# Files
# ===========================================================================


@mcp.tool()
async def list_files(
    created_since: Optional[str] = None,
    search_text: Optional[str] = None,
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
) -> Any:
    """List PracticePanther files. Filter by account, matter, activity, creator, search text."""
    return await api_get(
        "files",
        created_since=created_since,
        search_text=search_text,
        account_id=account_id,
        matter_id=matter_id,
        activity_id=activity_id,
        created_by_user_id=created_by_user_id,
    )


@mcp.tool()
async def get_file(id: str) -> Any:
    """Get PracticePanther file metadata by ID."""
    return await api_get(f"files/{id}")


@mcp.tool()
async def download_file(id: str) -> Any:
    """Download a PracticePanther file by ID. Returns hex-encoded content and content type."""
    return await api_request("GET", f"files/download/{id}", is_download=True)


@mcp.tool()
async def update_file(id: str, file_data: dict) -> Any:
    """Update PracticePanther file metadata."""
    return await api_put("files", id, file_data)


@mcp.tool()
async def delete_file(id: str) -> Any:
    """Delete a PracticePanther file by ID."""
    return await api_delete("files", id)


# ===========================================================================
# Items (Billing Rate Items)
# ===========================================================================


@mcp.tool()
async def list_items(
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther billing rate items."""
    return await api_get(
        "Items",
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_item(id: str) -> Any:
    """Get a single PracticePanther billing rate item by ID."""
    return await api_get(f"Items/{id}")


@mcp.tool()
async def create_item(item: dict) -> Any:
    """Create a new PracticePanther billing rate item. Provide name, code, description, rate."""
    return await api_post("Items", item)


@mcp.tool()
async def update_item(id: str, item: dict) -> Any:
    """Update an existing PracticePanther billing rate item."""
    return await api_put("Items", id, item)


@mcp.tool()
async def delete_item(id: str) -> Any:
    """Delete a PracticePanther billing rate item by ID."""
    return await api_delete("Items", id)


# ===========================================================================
# Bank Accounts
# ===========================================================================


@mcp.tool()
async def list_bank_accounts(
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther bank accounts."""
    return await api_get(
        "bankaccounts",
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_bank_account(id: str) -> Any:
    """Get a single PracticePanther bank account by ID."""
    return await api_get(f"bankaccounts/{id}")


@mcp.tool()
async def create_bank_account(bank_account: dict) -> Any:
    """Create a new PracticePanther bank account. Provide type and name."""
    return await api_post("bankaccounts", bank_account)


@mcp.tool()
async def update_bank_account(id: str, bank_account: dict) -> Any:
    """Update an existing PracticePanther bank account."""
    return await api_put("bankaccounts", id, bank_account)


@mcp.tool()
async def delete_bank_account(id: str) -> Any:
    """Delete a PracticePanther bank account by ID."""
    return await api_delete("bankaccounts", id)


# ===========================================================================
# Relationships
# ===========================================================================


@mcp.tool()
async def list_relationships(
    account_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    created_since: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Any:
    """List PracticePanther relationships."""
    return await api_get(
        "relationships",
        account_id=account_id,
        matter_id=matter_id,
        created_since=created_since,
        updated_since=updated_since,
    )


@mcp.tool()
async def get_relationship(id: str) -> Any:
    """Get a single PracticePanther relationship by ID."""
    return await api_get(f"relationships/{id}")


@mcp.tool()
async def create_relationship(relationship: dict) -> Any:
    """Create a new PracticePanther relationship."""
    return await api_post("relationships", relationship)


@mcp.tool()
async def update_relationship(id: str, relationship: dict) -> Any:
    """Update an existing PracticePanther relationship."""
    return await api_put("relationships", id, relationship)


@mcp.tool()
async def delete_relationship(id: str) -> Any:
    """Delete a PracticePanther relationship by ID."""
    return await api_delete("relationships", id)


# ===========================================================================
# Custom Fields
# ===========================================================================


@mcp.tool()
async def get_company_custom_fields() -> Any:
    """Get all PracticePanther custom fields for accounts/companies."""
    return await api_get("customfields/company")


@mcp.tool()
async def get_matter_custom_fields() -> Any:
    """Get all PracticePanther custom fields for matters."""
    return await api_get("customfields/matter")


@mcp.tool()
async def get_contact_custom_fields() -> Any:
    """Get all PracticePanther custom fields for contacts."""
    return await api_get("customfields/contact")


@mcp.tool()
async def get_custom_field(id: str) -> Any:
    """Get a single PracticePanther custom field by ID."""
    return await api_get(f"customfields/{id}")


# ===========================================================================
# Tags
# ===========================================================================


@mcp.tool()
async def get_account_tags() -> Any:
    """Get all PracticePanther account tags."""
    return await api_get("tags/account")


@mcp.tool()
async def get_matter_tags() -> Any:
    """Get all PracticePanther matter tags."""
    return await api_get("tags/matter")


@mcp.tool()
async def get_activity_tags() -> Any:
    """Get all PracticePanther activity tags."""
    return await api_get("tags/activity")


# ===========================================================================
# Users
# ===========================================================================


@mcp.tool()
async def get_current_user() -> Any:
    """Get the currently authenticated PracticePanther user."""
    return await api_get("users/me")


@mcp.tool()
async def get_user(id: str) -> Any:
    """Get a PracticePanther user by ID."""
    return await api_get(f"users/{id}")


@mcp.tool()
async def list_users() -> Any:
    """List all PracticePanther users."""
    return await api_get("users")


# ===========================================================================
# Starlette App (HTTP wrapper with OAuth callback)
# ===========================================================================


async def oauth_callback(request: Request):
    """Handle the OAuth callback from PracticePanther."""
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(f"<h1>Authorization Error</h1><p>{error}</p>", status_code=400)

    if not code:
        return HTMLResponse("<h1>Error</h1><p>No authorization code received.</p>", status_code=400)

    try:
        result = await exchange_code_for_tokens(code)
        return HTMLResponse(
            "<h1>PracticePanther Connected!</h1>"
            "<p>You can close this window and return to Claude.</p>"
            f"<p>Token expires in {result['expires_in']} seconds.</p>"
        )
    except Exception as e:
        return HTMLResponse(f"<h1>Token Exchange Error</h1><p>{e}</p>", status_code=500)


async def health(request: Request):
    return JSONResponse({"status": "ok", "server": "PracticePanther MCP"})


def create_app():
    """Create the Starlette app wrapping the MCP server."""
    mcp_app = mcp.streamable_http_app()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        # Run the MCP app's lifespan so the task group is initialized
        async with mcp_app.router.lifespan_context(app):
            yield

    app = Starlette(
        routes=[
            Route("/oauth/callback", oauth_callback),
            Route("/health", health),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port)
