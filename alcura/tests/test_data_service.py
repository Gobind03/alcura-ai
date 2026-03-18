"""Tests for the data_service module.

These tests validate the data retrieval and tool definition logic
without making actual OpenAI API calls.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura.services.data_service import (
	build_tool_definitions,
	dispatch_tool_call,
	fetch_records,
	get_distinct_values,
	get_indexed_doctypes,
	get_record_count,
)


class TestDataService(FrappeTestCase):

	def setUp(self):
		super().setUp()
		self._cleanup()
		self._create_test_index()

	def tearDown(self):
		self._cleanup()
		frappe.db.rollback()

	def _cleanup(self):
		if frappe.db.exists("AI DocType Index", "ToDo"):
			frappe.delete_doc("AI DocType Index", "ToDo", force=True)

	def _create_test_index(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": "ToDo",
				"description": "Tasks and to-do items",
				"max_records": 10,
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
					{"field_name": "description", "field_label": "Description", "field_type": "Text Editor"},
					{"field_name": "status", "field_label": "Status", "field_type": "Select"},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)

	def test_get_indexed_doctypes(self):
		result = get_indexed_doctypes()
		self.assertTrue(len(result) >= 1)
		todo_entry = next((d for d in result if d["doctype"] == "ToDo"), None)
		self.assertIsNotNone(todo_entry)
		self.assertEqual(todo_entry["description"], "Tasks and to-do items")
		self.assertEqual(len(todo_entry["fields"]), 3)

	def test_fetch_records_scoped_to_allowed_fields(self):
		records = fetch_records("ToDo", fields=["name", "description", "status"])
		if records:
			keys = set(records[0].keys())
			self.assertTrue(keys.issubset({"name", "description", "status"}))

	def test_fetch_records_filters_disallowed_fields(self):
		records = fetch_records("ToDo", fields=["name", "owner"])
		if records:
			keys = set(records[0].keys())
			self.assertNotIn("owner", keys)

	def test_fetch_records_respects_max_limit(self):
		records = fetch_records("ToDo", limit=9999)
		self.assertTrue(len(records) <= 10)

	def test_fetch_unindexed_doctype_raises(self):
		with self.assertRaises(ValueError):
			fetch_records("User")

	def test_get_record_count(self):
		count = get_record_count("ToDo")
		self.assertIsInstance(count, int)
		self.assertTrue(count >= 0)

	def test_get_distinct_values(self):
		values = get_distinct_values("ToDo", "status")
		self.assertIsInstance(values, list)

	def test_get_distinct_values_disallowed_field(self):
		with self.assertRaises(ValueError):
			get_distinct_values("ToDo", "owner")

	def test_build_tool_definitions(self):
		tools = build_tool_definitions()
		self.assertTrue(len(tools) == 4)
		tool_names = {t["function"]["name"] for t in tools}
		self.assertEqual(
			tool_names,
			{"fetch_records", "get_record_count", "get_distinct_values", "aggregate_data"},
		)
		for tool in tools:
			self.assertEqual(tool["type"], "function")
			params = tool["function"]["parameters"]
			self.assertIn("doctype", params["properties"])
			self.assertIn("ToDo", params["properties"]["doctype"]["enum"])

	def test_dispatch_fetch_records(self):
		result = dispatch_tool_call("fetch_records", {"doctype": "ToDo", "limit": 5})
		parsed = json.loads(result)
		self.assertIsInstance(parsed, list)

	def test_dispatch_get_record_count(self):
		result = dispatch_tool_call("get_record_count", {"doctype": "ToDo"})
		parsed = json.loads(result)
		self.assertIn("count", parsed)

	def test_dispatch_unknown_tool_raises(self):
		with self.assertRaises(ValueError):
			dispatch_tool_call("nonexistent_tool", {})
