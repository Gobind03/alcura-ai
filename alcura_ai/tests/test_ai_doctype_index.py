"""Tests for the AI DocType Index DocType."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAIDocTypeIndex(FrappeTestCase):

	def tearDown(self):
		frappe.db.rollback()

	def _make_index(self, doctype="ToDo", **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": doctype,
				"description": f"Test index for {doctype}",
				"max_records": 50,
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
					{"field_name": "description", "field_label": "Description", "field_type": "Text Editor"},
					{"field_name": "status", "field_label": "Status", "field_type": "Select"},
				],
				**kwargs,
			}
		)
		doc.insert(ignore_if_duplicate=True)
		return doc

	def test_create_index(self):
		doc = self._make_index()
		self.assertEqual(doc.reference_doctype, "ToDo")
		self.assertEqual(doc.enabled, 1)
		self.assertEqual(len(doc.index_fields), 3)

	def test_invalid_doctype_raises(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._make_index(doctype="Nonexistent DocType 12345")

	def test_invalid_field_raises(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.get_doc(
				{
				"doctype": "AI DocType Index",
				"reference_doctype": "ToDo",
				"description": "Test",
				"enabled": 1,
				"index_fields": [
					{"field_name": "totally_fake_field", "field_label": "Fake", "field_type": "Data"},
				],
				}
			).insert()

	def test_populate_fields(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": "ToDo",
				"description": "Test populate",
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)
		doc.populate_fields()

		field_names = [f.field_name for f in doc.index_fields]
		self.assertIn("name", field_names)
		self.assertIn("status", field_names)
		self.assertTrue(len(doc.index_fields) > 1)

	def test_populate_fields_includes_child_tables(self):
		"""Fields from child tables should appear with dotted notation."""
		dt_with_children = self._find_doctype_with_child_table()
		if not dt_with_children:
			self.skipTest("No suitable DocType with child tables found")

		doctype, table_fieldname, child_dt = dt_with_children
		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": doctype,
				"description": f"Test child table populate for {doctype}",
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)
		doc.populate_fields()

		field_names = [f.field_name for f in doc.index_fields]

		child_meta = frappe.get_meta(child_dt)
		child_data_fields = [
			f for f in child_meta.fields
			if f.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Fold"}
		]
		self.assertTrue(child_data_fields, f"Child DocType {child_dt} should have data fields")

		dotted_fields = [fn for fn in field_names if fn.startswith(f"{table_fieldname}.")]
		self.assertTrue(dotted_fields, "Child table fields should be populated with dotted notation")
		self.assertEqual(len(dotted_fields), len(child_data_fields))

		first_child_field = child_data_fields[0]
		expected_name = f"{table_fieldname}.{first_child_field.fieldname}"
		self.assertIn(expected_name, field_names)

		row = next(r for r in doc.index_fields if r.field_name == expected_name)
		self.assertIn("→", row.field_label)

	def test_populate_fields_no_table_rows_in_parent(self):
		"""Table-type fields themselves should not appear as rows; only their children should."""
		dt_with_children = self._find_doctype_with_child_table()
		if not dt_with_children:
			self.skipTest("No suitable DocType with child tables found")

		doctype, table_fieldname, _ = dt_with_children
		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": doctype,
				"description": f"Test no table rows for {doctype}",
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)
		doc.populate_fields()

		field_names = [f.field_name for f in doc.index_fields]
		self.assertNotIn(table_fieldname, field_names)

	def test_validate_child_table_field_accepted(self):
		"""Dotted child-table field names should pass validation."""
		dt_with_children = self._find_doctype_with_child_table()
		if not dt_with_children:
			self.skipTest("No suitable DocType with child tables found")

		doctype, table_fieldname, child_dt = dt_with_children
		child_meta = frappe.get_meta(child_dt)
		child_field = next(
			f for f in child_meta.fields
			if f.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Fold"}
		)

		doc = frappe.get_doc(
			{
				"doctype": "AI DocType Index",
				"reference_doctype": doctype,
				"description": f"Test child field validation for {doctype}",
				"enabled": 1,
				"index_fields": [
					{"field_name": "name", "field_label": "ID", "field_type": "Data"},
					{
						"field_name": f"{table_fieldname}.{child_field.fieldname}",
						"field_label": child_field.label or child_field.fieldname,
						"field_type": child_field.fieldtype,
					},
				],
			}
		)
		doc.insert(ignore_if_duplicate=True)

	def test_invalid_child_table_field_raises(self):
		"""Invalid dotted field name should fail validation."""
		dt_with_children = self._find_doctype_with_child_table()
		if not dt_with_children:
			self.skipTest("No suitable DocType with child tables found")

		doctype, table_fieldname, _ = dt_with_children
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.get_doc(
				{
					"doctype": "AI DocType Index",
					"reference_doctype": doctype,
					"description": "Test invalid child field",
					"enabled": 1,
					"index_fields": [
						{
							"field_name": f"{table_fieldname}.nonexistent_field_xyz",
							"field_label": "Fake",
							"field_type": "Data",
						},
					],
				}
			).insert()

	@staticmethod
	def _find_doctype_with_child_table():
		"""Return (doctype, table_fieldname, child_dt) for a core DocType with a child table."""
		for dt in ("User", "Web Form", "Workflow", "Event"):
			if not frappe.db.exists("DocType", dt):
				continue
			meta = frappe.get_meta(dt)
			for f in meta.fields:
				if f.fieldtype in ("Table", "Table MultiSelect") and f.options:
					return (dt, f.fieldname, f.options)
		return None


class TestAlcuraAISettings(FrappeTestCase):

	def tearDown(self):
		frappe.db.rollback()

	def test_settings_exists_as_single(self):
		doc = frappe.get_single("Alcura AI Settings")
		self.assertIsNotNone(doc)

	def test_invalid_temperature_raises(self):
		doc = frappe.get_single("Alcura AI Settings")
		doc.temperature = 3.0
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.validate()

	def test_valid_temperature(self):
		doc = frappe.get_single("Alcura AI Settings")
		doc.temperature = 0.5
		doc.validate()
