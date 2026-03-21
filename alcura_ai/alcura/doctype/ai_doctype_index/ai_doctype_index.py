import frappe
from frappe.model.document import Document

SKIP_FIELDTYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Fold"}


@frappe.whitelist()
def get_doctype_fields(doctype):
	"""Return field metadata (name, label, type) for a DocType including child table fields."""
	if not frappe.db.exists("DocType", doctype):
		frappe.throw(f"DocType '{doctype}' does not exist.")

	meta = frappe.get_meta(doctype)
	fields = [{"field_name": "name", "field_label": "ID", "field_type": "Data"}]
	child_tables = []

	for field in meta.fields:
		if field.fieldtype in SKIP_FIELDTYPES:
			continue

		if field.fieldtype in ("Table", "Table MultiSelect") and field.options:
			child_tables.append((field.fieldname, field.label or field.fieldname, field.options))
			continue

		fields.append({
			"field_name": field.fieldname,
			"field_label": field.label or field.fieldname,
			"field_type": field.fieldtype,
		})

	for table_fieldname, table_label, child_dt in child_tables:
		child_meta = frappe.get_meta(child_dt)
		for cf in child_meta.fields:
			if cf.fieldtype in SKIP_FIELDTYPES:
				continue
			fields.append({
				"field_name": f"{table_fieldname}.{cf.fieldname}",
				"field_label": f"{table_label} → {cf.label or cf.fieldname}",
				"field_type": cf.fieldtype,
			})

	return fields


class AIDocTypeIndex(Document):

	def validate(self):
		self._validate_doctype_exists()
		self._validate_fields()

	def _validate_doctype_exists(self):
		if not frappe.db.exists("DocType", self.reference_doctype):
			frappe.throw(f"DocType '{self.reference_doctype}' does not exist.")

	def _validate_fields(self):
		meta = frappe.get_meta(self.reference_doctype)
		valid_fieldnames = {"name"}

		child_table_map = {}
		for f in meta.fields:
			valid_fieldnames.add(f.fieldname)
			if f.fieldtype in ("Table", "Table MultiSelect") and f.options:
				child_table_map[f.fieldname] = f.options

		for table_fieldname, child_dt in child_table_map.items():
			child_meta = frappe.get_meta(child_dt)
			for cf in child_meta.fields:
				if cf.fieldtype not in SKIP_FIELDTYPES:
					valid_fieldnames.add(f"{table_fieldname}.{cf.fieldname}")

		for row in self.index_fields:
			if row.field_name not in valid_fieldnames:
				frappe.throw(
					f"Field '{row.field_name}' does not exist in DocType '{self.reference_doctype}'."
				)

	@frappe.whitelist()
	def populate_fields(self):
		"""Auto-populate the fields table from the reference DocType and its child tables."""
		meta = frappe.get_meta(self.reference_doctype)
		self.index_fields = []

		self.append("index_fields", {
			"field_name": "name",
			"field_label": "ID",
			"field_type": "Data",
		})

		child_tables = []

		for field in meta.fields:
			if field.fieldtype in SKIP_FIELDTYPES:
				continue

			if field.fieldtype in ("Table", "Table MultiSelect") and field.options:
				child_tables.append((field.fieldname, field.label or field.fieldname, field.options))
				continue

			self.append("index_fields", {
				"field_name": field.fieldname,
				"field_label": field.label or field.fieldname,
				"field_type": field.fieldtype,
			})

		for table_fieldname, table_label, child_dt in child_tables:
			child_meta = frappe.get_meta(child_dt)
			for cf in child_meta.fields:
				if cf.fieldtype in SKIP_FIELDTYPES:
					continue
				self.append("index_fields", {
					"field_name": f"{table_fieldname}.{cf.fieldname}",
					"field_label": f"{table_label} → {cf.label or cf.fieldname}",
					"field_type": cf.fieldtype,
				})
