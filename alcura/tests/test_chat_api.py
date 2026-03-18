"""Tests for the chat API endpoint.

These tests validate request validation and context retrieval
without requiring a live OpenAI API key.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura.api.v1.chat import get_context


class TestChatGetContext(FrappeTestCase):

	def setUp(self):
		super().setUp()
		self._cleanup()

	def tearDown(self):
		self._cleanup()
		frappe.db.rollback()

	def _cleanup(self):
		if frappe.db.exists("AI DocType Index", "ToDo"):
			frappe.delete_doc("AI DocType Index", "ToDo", force=True)

	def _create_test_index(self):
		frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": "ToDo",
				"description": "Task items",
				"max_records": 50,
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
					{"field_name": "status", "field_label": "Status", "field_type": "Select"},
				],
			}
		).insert(ignore_if_duplicate=True)

	def test_get_context_empty(self):
		result = get_context()
		self.assertIn("doctypes", result)
		self.assertIsInstance(result["doctypes"], list)

	def test_get_context_with_index(self):
		self._create_test_index()
		result = get_context()
		doctypes = result["doctypes"]
		self.assertTrue(len(doctypes) >= 1)
		todo_entry = next((d for d in doctypes if d["doctype"] == "ToDo"), None)
		self.assertIsNotNone(todo_entry)
		self.assertEqual(todo_entry["description"], "Task items")
		self.assertEqual(todo_entry["field_count"], 2)


class TestChatSendMessageValidation(FrappeTestCase):
	"""Test input validation for send_message (no OpenAI calls)."""

	def test_empty_message_raises(self):
		from alcura.api.v1.chat import send_message

		with self.assertRaises(frappe.exceptions.ValidationError):
			send_message(message="")

	def test_disabled_ai_raises(self):
		from alcura.api.v1.chat import send_message

		settings = frappe.get_single("Alcura AI Settings")
		settings.enabled = 0
		settings.save()

		with self.assertRaises(frappe.exceptions.ValidationError):
			send_message(message="Hello")
