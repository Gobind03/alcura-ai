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
