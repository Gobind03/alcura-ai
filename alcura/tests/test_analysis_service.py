"""Tests for the analysis_service module (sandboxed code interpreter).

These tests validate the sandboxed Python execution environment,
security restrictions, chart generation, and error handling.
"""

import base64
import json

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura.services.analysis_service import dispatch_analysis, run_analysis


class TestAnalysisServiceExecution(FrappeTestCase):
	"""Tests for basic code execution and output capture."""

	def test_basic_print(self):
		result = run_analysis('print("hello world")', datasets={})
		self.assertEqual(result["output"].strip(), "hello world")
		self.assertEqual(result["charts"], [])

	def test_multi_line_print(self):
		code = 'print("line1")\nprint("line2")'
		result = run_analysis(code, datasets={})
		self.assertIn("line1", result["output"])
		self.assertIn("line2", result["output"])

	def test_empty_code(self):
		result = run_analysis("", datasets={})
		self.assertEqual(result["output"], "")
		self.assertEqual(result["charts"], [])

	def test_math_operations(self):
		code = 'import math\nprint(math.sqrt(144))'
		result = run_analysis(code, datasets={})
		self.assertIn("12.0", result["output"])

	def test_statistics_module(self):
		code = 'import statistics\nprint(statistics.mean([1, 2, 3, 4, 5]))'
		result = run_analysis(code, datasets={})
		self.assertIn("3", result["output"])

	def test_datetime_module(self):
		code = 'import datetime\nprint(type(datetime.date.today()).__name__)'
		result = run_analysis(code, datasets={})
		self.assertIn("date", result["output"])

	def test_collections_module(self):
		code = 'import collections\nc = collections.Counter([1,1,2,3])\nprint(c[1])'
		result = run_analysis(code, datasets={})
		self.assertIn("2", result["output"])

	def test_pandas_available(self):
		code = 'import pandas as pd\ndf = pd.DataFrame({"a": [1,2,3]})\nprint(len(df))'
		result = run_analysis(code, datasets={})
		self.assertIn("3", result["output"])

	def test_numpy_available(self):
		code = 'import numpy as np\nprint(np.mean([10, 20, 30]))'
		result = run_analysis(code, datasets={})
		self.assertIn("20.0", result["output"])

	def test_pd_and_np_preloaded(self):
		code = 'df = pd.DataFrame({"x": [1,2,3]})\nprint(np.sum(df["x"]))'
		result = run_analysis(code, datasets={})
		self.assertIn("6", result["output"])

	def test_pandas_groupby(self):
		code = (
			'df = pd.DataFrame({"cat": ["a","a","b"], "val": [10,20,30]})\n'
			'print(df.groupby("cat")["val"].sum().to_dict())'
		)
		result = run_analysis(code, datasets={})
		self.assertIn("a", result["output"])
		self.assertIn("30", result["output"])

	def test_pandas_describe(self):
		code = (
			'df = pd.DataFrame({"v": [1,2,3,4,5]})\n'
			'print(df["v"].describe())'
		)
		result = run_analysis(code, datasets={})
		self.assertIn("mean", result["output"])


class TestAnalysisServiceCharts(FrappeTestCase):
	"""Tests for matplotlib chart generation."""

	def test_single_chart(self):
		code = (
			'plt.figure()\n'
			'plt.bar(["A", "B", "C"], [10, 20, 30])\n'
			'plt.title("Test")\n'
			'print("done")'
		)
		result = run_analysis(code, datasets={})
		self.assertEqual(len(result["charts"]), 1)
		img_data = result["charts"][0]["image_base64"]
		decoded = base64.b64decode(img_data)
		self.assertTrue(decoded[:4] == b"\x89PNG")

	def test_multiple_charts(self):
		code = (
			'plt.figure()\n'
			'plt.plot([1,2,3])\n'
			'plt.figure()\n'
			'plt.bar([1,2],[3,4])\n'
			'print("two charts")'
		)
		result = run_analysis(code, datasets={})
		self.assertEqual(len(result["charts"]), 2)
		for chart in result["charts"]:
			self.assertIn("image_base64", chart)
			self.assertIn("title", chart)

	def test_no_chart_when_none_created(self):
		result = run_analysis('x = 1 + 1\nprint(x)', datasets={})
		self.assertEqual(result["charts"], [])


class TestAnalysisServiceSecurity(FrappeTestCase):
	"""Tests for sandbox security restrictions."""

	def test_open_blocked(self):
		result = run_analysis('open("/etc/passwd")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_dunder_import_blocked(self):
		result = run_analysis('__import__("os")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_eval_blocked(self):
		result = run_analysis('eval("1+1")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_exec_blocked(self):
		result = run_analysis('exec("x=1")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_compile_blocked(self):
		result = run_analysis('compile("x=1", "<>", "exec")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_import_os_blocked(self):
		result = run_analysis('import os\nos.listdir("/")', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_import_subprocess_blocked(self):
		result = run_analysis('import subprocess\nsubprocess.run(["ls"])', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_import_socket_blocked(self):
		result = run_analysis('import socket', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_import_shutil_blocked(self):
		result = run_analysis('import shutil', datasets={})
		self.assertIn("ERROR", result["output"])


class TestAnalysisServiceErrors(FrappeTestCase):
	"""Tests for error handling in code execution."""

	def test_zero_division_error(self):
		result = run_analysis('x = 1 / 0', datasets={})
		self.assertIn("ERROR", result["output"])
		self.assertIn("ZeroDivisionError", result["output"])

	def test_key_error(self):
		result = run_analysis('d = {}\nprint(d["missing"])', datasets={})
		self.assertIn("ERROR", result["output"])
		self.assertIn("KeyError", result["output"])

	def test_name_error(self):
		result = run_analysis('print(undefined_variable)', datasets={})
		self.assertIn("ERROR", result["output"])
		self.assertIn("NameError", result["output"])

	def test_syntax_error(self):
		result = run_analysis('def :', datasets={})
		self.assertIn("ERROR", result["output"])

	def test_partial_output_before_error(self):
		code = 'print("before")\nx = 1/0'
		result = run_analysis(code, datasets={})
		self.assertIn("before", result["output"])
		self.assertIn("ERROR", result["output"])


class TestAnalysisServiceDatasets(FrappeTestCase):
	"""Tests for dataset loading into the sandbox."""

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
		frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": "ToDo",
				"description": "Tasks",
				"max_records": 50,
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
					{"field_name": "status", "field_label": "Status", "field_type": "Select"},
				],
			}
		).insert(ignore_if_duplicate=True)

	def test_dataset_loaded_as_dataframe(self):
		code = 'print(type(todos).__name__)\nprint(list(todos.columns))'
		result = run_analysis(
			code,
			datasets={"todos": {"doctype": "ToDo", "fields": ["name", "status"]}},
		)
		self.assertIn("DataFrame", result["output"])

	def test_dataset_operations(self):
		code = 'print(len(todos))'
		result = run_analysis(
			code,
			datasets={"todos": {"doctype": "ToDo"}},
		)
		self.assertNotIn("ERROR", result["output"])

	def test_unindexed_doctype_raises(self):
		with self.assertRaises(ValueError):
			run_analysis(
				'print(len(data))',
				datasets={"data": {"doctype": "User"}},
			)

	def test_missing_doctype_raises(self):
		with self.assertRaises(ValueError):
			run_analysis(
				'print("hi")',
				datasets={"data": {"filters": {"status": "Open"}}},
			)


class TestDispatchAnalysis(FrappeTestCase):
	"""Tests for the dispatch_analysis helper."""

	def test_dispatch_returns_tuple(self):
		result_json, charts = dispatch_analysis({"code": 'print("ok")', "datasets": {}})
		parsed = json.loads(result_json)
		self.assertIn("output", parsed)
		self.assertIsInstance(charts, list)

	def test_dispatch_empty_code(self):
		result_json, charts = dispatch_analysis({"code": "", "datasets": {}})
		parsed = json.loads(result_json)
		self.assertEqual(parsed["output"], "")
		self.assertEqual(charts, [])

	def test_dispatch_with_chart(self):
		code = 'plt.figure()\nplt.plot([1,2,3])\nprint("charted")'
		result_json, charts = dispatch_analysis({"code": code, "datasets": {}})
		parsed = json.loads(result_json)
		self.assertIn("charted", parsed["output"])
		self.assertEqual(len(charts), 1)
