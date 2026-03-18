import frappe
from frappe.model.document import Document


class AIDocTypeIndex(Document):

	def validate(self):
		self._validate_doctype_exists()
		self._validate_fields()

	def _validate_doctype_exists(self):
		if not frappe.db.exists("DocType", self.reference_doctype):
			frappe.throw(f"DocType '{self.reference_doctype}' does not exist.")

	def _validate_fields(self):
		meta = frappe.get_meta(self.reference_doctype)
		valid_fieldnames = {f.fieldname for f in meta.fields}
		valid_fieldnames.add("name")

		for row in self.index_fields:
			if row.field_name not in valid_fieldnames:
				frappe.throw(
					f"Field '{row.field_name}' does not exist in DocType '{self.reference_doctype}'."
				)

	@frappe.whitelist()
	def populate_fields(self):
		"""Auto-populate the fields table from the reference DocType's meta."""
		meta = frappe.get_meta(self.reference_doctype)
		self.index_fields = []

		skip_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Fold"}

		for field in meta.fields:
			if field.fieldtype in skip_types:
				continue
			self.index_fields.append(
				{
					"field_name": field.fieldname,
					"field_label": field.label or field.fieldname,
					"field_type": field.fieldtype,
				}
			)

		self.index_fields.insert(
			0,
			{
				"field_name": "name",
				"field_label": "ID",
				"field_type": "Data",
			},
		)
