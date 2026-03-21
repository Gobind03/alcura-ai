"""Tests for the data_service module.

These tests validate the data retrieval and tool definition logic
without making actual OpenAI API calls.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura_ai.services.data_service import (
	_build_sql_where,
	aggregate_data,
	build_tool_definitions,
	date_series,
	dispatch_tool_call,
	fetch_records,
	get_distinct_values,
	get_indexed_doctypes,
	get_record_count,
	statistical_summary,
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
					{"field_name": "date", "field_label": "Date", "field_type": "Date"},
					{"field_name": "priority", "field_label": "Priority", "field_type": "Select"},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)

	# ── Original tests ────────────────────────────────────────────

	def test_get_indexed_doctypes(self):
		result = get_indexed_doctypes()
		self.assertTrue(len(result) >= 1)
		todo_entry = next((d for d in result if d["doctype"] == "ToDo"), None)
		self.assertIsNotNone(todo_entry)
		self.assertEqual(todo_entry["description"], "Tasks and to-do items")
		self.assertEqual(len(todo_entry["fields"]), 5)

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

	# ── Enhanced filter tests ─────────────────────────────────────

	def test_build_sql_where_dict_filters(self):
		where, values = _build_sql_where({"status": "Open"}, {"status", "name"})
		self.assertIn("WHERE", where)
		self.assertTrue(len(values) > 0)

	def test_build_sql_where_list_filters(self):
		where, values = _build_sql_where(
			[["status", "=", "Open"]],
			{"status", "name"},
		)
		self.assertIn("WHERE", where)
		self.assertIn("=", where)

	def test_build_sql_where_between_operator(self):
		where, values = _build_sql_where(
			[["date", "between", ["2025-01-01", "2025-12-31"]]],
			{"date", "name"},
		)
		self.assertIn("BETWEEN", where)
		self.assertEqual(len(values), 2)

	def test_build_sql_where_in_operator(self):
		where, values = _build_sql_where(
			[["status", "in", ["Open", "Closed"]]],
			{"status", "name"},
		)
		self.assertIn("IN", where)

	def test_build_sql_where_like_operator(self):
		where, values = _build_sql_where(
			[["description", "like", "%test%"]],
			{"description", "name"},
		)
		self.assertIn("LIKE", where)

	def test_build_sql_where_comparison_operators(self):
		for op in [">", "<", ">=", "<=", "!="]:
			where, values = _build_sql_where(
				[["name", op, "test"]],
				{"name"},
			)
			self.assertIn("WHERE", where)

	def test_build_sql_where_disallowed_field_raises(self):
		with self.assertRaises(ValueError):
			_build_sql_where([["owner", "=", "Admin"]], {"status", "name"})

	def test_build_sql_where_unsupported_operator_raises(self):
		with self.assertRaises(ValueError):
			_build_sql_where([["status", "INVALID", "Open"]], {"status", "name"})

	def test_build_sql_where_empty_filters(self):
		where, values = _build_sql_where({}, {"status", "name"})
		self.assertEqual(where, "")
		self.assertEqual(values, {})

	def test_fetch_records_with_list_filters(self):
		records = fetch_records(
			"ToDo",
			filters=[["status", "=", "Open"]],
			fields=["name", "status"],
		)
		self.assertIsInstance(records, list)

	# ── Tool definitions ──────────────────────────────────────────

	def test_build_tool_definitions(self):
		tools = build_tool_definitions()
		self.assertEqual(len(tools), 7)
		tool_names = {t["function"]["name"] for t in tools}
		self.assertEqual(
			tool_names,
			{
				"fetch_records", "get_record_count", "get_distinct_values",
				"aggregate_data", "date_series", "statistical_summary",
				"run_analysis",
			},
		)
		for tool in tools:
			self.assertEqual(tool["type"], "function")
			fn = tool["function"]
			self.assertIn("name", fn)
			self.assertIn("parameters", fn)
			if fn["name"] != "run_analysis":
				params = fn["parameters"]
				self.assertIn("doctype", params["properties"])
				self.assertIn("ToDo", params["properties"]["doctype"]["enum"])

	# ── date_series tests ─────────────────────────────────────────

	def test_date_series_by_month(self):
		result = date_series("ToDo", date_field="date", period="month")
		self.assertIsInstance(result, list)

	def test_date_series_by_year(self):
		result = date_series("ToDo", date_field="date", period="year")
		self.assertIsInstance(result, list)

	def test_date_series_by_quarter(self):
		result = date_series("ToDo", date_field="date", period="quarter")
		self.assertIsInstance(result, list)

	def test_date_series_invalid_period_raises(self):
		with self.assertRaises(ValueError):
			date_series("ToDo", date_field="date", period="century")

	def test_date_series_disallowed_field_raises(self):
		with self.assertRaises(ValueError):
			date_series("ToDo", date_field="owner", period="month")

	def test_date_series_unindexed_doctype_raises(self):
		with self.assertRaises(ValueError):
			date_series("User", date_field="creation", period="month")

	def test_dispatch_date_series(self):
		result = dispatch_tool_call(
			"date_series",
			{"doctype": "ToDo", "date_field": "date", "period": "month"},
		)
		parsed = json.loads(result)
		self.assertIsInstance(parsed, list)

	# ── statistical_summary tests ─────────────────────────────────

	def test_statistical_summary_returns_all_keys(self):
		result = statistical_summary("ToDo", field="name")
		expected_keys = {"count", "sum", "avg", "min", "max", "stddev", "p25", "median", "p75"}
		self.assertTrue(expected_keys.issubset(set(result.keys())))

	def test_statistical_summary_disallowed_field_raises(self):
		with self.assertRaises(ValueError):
			statistical_summary("ToDo", field="owner")

	def test_statistical_summary_unindexed_doctype_raises(self):
		with self.assertRaises(ValueError):
			statistical_summary("User", field="name")

	def test_dispatch_statistical_summary(self):
		result = dispatch_tool_call(
			"statistical_summary",
			{"doctype": "ToDo", "field": "name"},
		)
		parsed = json.loads(result)
		self.assertIn("count", parsed)
		self.assertIn("median", parsed)

	# ── Enhanced aggregate_data tests ─────────────────────────────

	def test_aggregate_data_single(self):
		result = aggregate_data("ToDo", field="*", function="COUNT")
		self.assertIsInstance(result, list)
		self.assertTrue(len(result) >= 1)
		self.assertIn("result", result[0])

	def test_aggregate_data_multi(self):
		result = aggregate_data(
			"ToDo",
			field="*",
			aggregations=[
				{"field": "*", "function": "COUNT"},
				{"field": "name", "function": "MIN"},
			],
		)
		self.assertIsInstance(result, list)
		self.assertTrue(len(result) >= 1)
		self.assertIn("result_0", result[0])
		self.assertIn("result_1", result[0])

	def test_aggregate_data_with_list_filters(self):
		result = aggregate_data(
			"ToDo",
			field="*",
			function="COUNT",
			filters=[["status", "=", "Open"]],
		)
		self.assertIsInstance(result, list)

	def test_aggregate_data_unsupported_function_raises(self):
		with self.assertRaises(ValueError):
			aggregate_data("ToDo", field="*", function="MEDIAN")
