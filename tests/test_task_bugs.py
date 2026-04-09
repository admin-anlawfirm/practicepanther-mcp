"""Regression tests for two task-related bugs reported in production.

Bug 1 — ``create_task`` accepts ``status: null`` and persists it, which breaks
PP's web UI. Fix: default ``status`` to ``"NotCompleted"`` when omitted or null.

Bug 2 — ``update_task`` (and every other ``update_*`` tool) was a full-replace
PUT, so a partial payload like ``{status, notes}`` wiped ``matter_ref`` and
``account_ref``, silently orphaning the task. Fix: ``api_put_merge`` reads the
existing object, strips server-managed fields, merges the caller's partial
payload on top, and PUTs the result.

Run with::

    python -m unittest tests.test_task_bugs
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Make the project root importable when running tests directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pp_client  # noqa: E402
import server  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


class CreateTaskStatusDefaultTests(unittest.TestCase):
    """Bug 1: create_task must never let a null/omitted status reach PP."""

    def test_missing_status_defaults_to_not_completed(self):
        with patch("server.api_post", new=AsyncMock(return_value={"id": "t1"})) as mock_post:
            _run(server.create_task({"subject": "Test", "matter_ref": {"id": "m1"}}))
        sent_body = mock_post.call_args.args[1]
        self.assertEqual(sent_body["status"], "NotCompleted")
        # Caller's original fields must still be present.
        self.assertEqual(sent_body["subject"], "Test")
        self.assertEqual(sent_body["matter_ref"], {"id": "m1"})

    def test_explicit_null_status_defaults_to_not_completed(self):
        with patch("server.api_post", new=AsyncMock(return_value={"id": "t1"})) as mock_post:
            _run(server.create_task({"subject": "Test", "status": None}))
        sent_body = mock_post.call_args.args[1]
        self.assertEqual(sent_body["status"], "NotCompleted")

    def test_explicit_status_is_preserved(self):
        with patch("server.api_post", new=AsyncMock(return_value={"id": "t1"})) as mock_post:
            _run(server.create_task({"subject": "Test", "status": "Completed"}))
        sent_body = mock_post.call_args.args[1]
        self.assertEqual(sent_body["status"], "Completed")

    def test_caller_dict_is_not_mutated(self):
        """Defaulting status must not mutate the caller's dict in place."""
        caller_payload = {"subject": "Test"}
        with patch("server.api_post", new=AsyncMock(return_value={"id": "t1"})):
            _run(server.create_task(caller_payload))
        self.assertNotIn("status", caller_payload)


class UpdateTaskMergeTests(unittest.TestCase):
    """Bug 2: update_task must preserve fields the caller did not send."""

    EXISTING_TASK = {
        "id": "t1",
        "subject": "Draft motion to compel",
        "notes": "original notes",
        "status": "NotCompleted",
        "priority": "High",
        "due_date": "2026-05-01T00:00:00Z",
        "matter_ref": {"id": "m1", "display_name": "Smith v. Jones"},
        "account_ref": {"id": "a1", "display_name": "Smith, Jane"},
        "assigned_to_users": [{"id": "u1", "display_name": "Alberto"}],
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
    }

    def _patched_api_request(self, put_response=None):
        """Return a mock that returns EXISTING_TASK on GET and put_response on PUT."""
        mock = AsyncMock()
        mock.side_effect = [dict(self.EXISTING_TASK), put_response or {"ok": True}]
        return mock

    def test_partial_update_preserves_matter_and_account(self):
        """The exact repro from the bug report."""
        mock_req = self._patched_api_request()
        with patch("pp_client.api_request", new=mock_req):
            _run(pp_client.api_put_merge("tasks", "t1", {"status": "Completed", "notes": "done"}))

        # Two calls: GET then PUT.
        self.assertEqual(mock_req.call_count, 2)
        get_call, put_call = mock_req.call_args_list

        self.assertEqual(get_call.args[0], "GET")
        self.assertEqual(get_call.args[1], "tasks/t1")

        self.assertEqual(put_call.args[0], "PUT")
        self.assertEqual(put_call.args[1], "tasks")
        self.assertEqual(put_call.kwargs["params"], {"id": "t1"})

        sent = put_call.kwargs["json_body"]

        # Critical: matter_ref and account_ref must survive the partial update.
        self.assertEqual(sent["matter_ref"], {"id": "m1", "display_name": "Smith v. Jones"})
        self.assertEqual(sent["account_ref"], {"id": "a1", "display_name": "Smith, Jane"})

        # Other untouched fields must also survive.
        self.assertEqual(sent["subject"], "Draft motion to compel")
        self.assertEqual(sent["priority"], "High")
        self.assertEqual(sent["due_date"], "2026-05-01T00:00:00Z")
        self.assertEqual(sent["assigned_to_users"], [{"id": "u1", "display_name": "Alberto"}])

        # Caller's fields applied on top.
        self.assertEqual(sent["status"], "Completed")
        self.assertEqual(sent["notes"], "done")

        # Server-managed fields must be stripped from the echo-back.
        self.assertNotIn("id", sent)
        self.assertNotIn("created_at", sent)
        self.assertNotIn("updated_at", sent)

    def test_caller_can_override_existing_scalar_field(self):
        mock_req = self._patched_api_request()
        with patch("pp_client.api_request", new=mock_req):
            _run(pp_client.api_put_merge("tasks", "t1", {"subject": "New subject"}))

        sent = mock_req.call_args_list[1].kwargs["json_body"]
        self.assertEqual(sent["subject"], "New subject")
        # Other fields unchanged.
        self.assertEqual(sent["status"], "NotCompleted")
        self.assertEqual(sent["matter_ref"], {"id": "m1", "display_name": "Smith v. Jones"})

    def test_caller_can_override_ref_field(self):
        """A caller who *does* want to change matter_ref can still do so."""
        mock_req = self._patched_api_request()
        new_matter = {"id": "m2", "display_name": "Other matter"}
        with patch("pp_client.api_request", new=mock_req):
            _run(pp_client.api_put_merge("tasks", "t1", {"matter_ref": new_matter}))

        sent = mock_req.call_args_list[1].kwargs["json_body"]
        self.assertEqual(sent["matter_ref"], new_matter)

    def test_empty_partial_payload_is_a_no_op_echo(self):
        """An empty partial should still round-trip every field untouched."""
        mock_req = self._patched_api_request()
        with patch("pp_client.api_request", new=mock_req):
            _run(pp_client.api_put_merge("tasks", "t1", {}))

        sent = mock_req.call_args_list[1].kwargs["json_body"]
        self.assertEqual(sent["matter_ref"], {"id": "m1", "display_name": "Smith v. Jones"})
        self.assertEqual(sent["status"], "NotCompleted")
        self.assertNotIn("id", sent)

    def test_non_object_get_response_raises(self):
        """If GET returns something weird (e.g. a list), bail out rather than corrupting data."""
        mock_req = AsyncMock()
        mock_req.side_effect = [["not", "an", "object"]]
        with patch("pp_client.api_request", new=mock_req):
            with self.assertRaises(RuntimeError):
                _run(pp_client.api_put_merge("tasks", "t1", {"status": "Completed"}))


if __name__ == "__main__":
    unittest.main()
