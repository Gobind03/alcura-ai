frappe.ui.form.on("AI DocType Index", {
	refresh(frm) {
		if (frm.doc.reference_doctype) {
			frm.add_custom_button(__("Populate Fields"), () => {
				frm.call("populate_fields").then(() => {
					frm.dirty();
					frm.refresh_fields();
					set_field_name_options(frm);
					frappe.show_alert({
						message: __("Fields populated from {0}", [frm.doc.reference_doctype]),
						indicator: "green",
					});
				});
			});

			set_field_name_options(frm);
		}
	},

	reference_doctype(frm) {
		if (frm.doc.reference_doctype) {
			frm._doctype_fields_map = null;
			set_field_name_options(frm);

			if (!frm.doc.index_fields?.length) {
				frm.call("populate_fields").then(() => {
					frm.dirty();
					frm.refresh_fields();
					set_field_name_options(frm);
				});
			}
		}
	},
});

frappe.ui.form.on("AI DocType Index Field", {
	field_name(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.field_name && frm._doctype_fields_map) {
			let field_info = frm._doctype_fields_map[row.field_name];
			if (field_info) {
				frappe.model.set_value(cdt, cdn, "field_label", field_info.field_label);
				frappe.model.set_value(cdt, cdn, "field_type", field_info.field_type);
			}
		}
	},
});

function set_field_name_options(frm) {
	if (!frm.doc.reference_doctype) return;

	frappe.call({
		method: "alcura_ai.alcura.doctype.ai_doctype_index.ai_doctype_index.get_doctype_fields",
		args: { doctype: frm.doc.reference_doctype },
		callback(r) {
			if (!r.message) return;

			let fields = r.message;
			frm._doctype_fields_map = {};
			let options = [""];

			fields.forEach((f) => {
				options.push(f.field_name);
				frm._doctype_fields_map[f.field_name] = f;
			});

			frm.fields_dict.index_fields.grid.update_docfield_property(
				"field_name",
				"options",
				options.join("\n")
			);
			frm.fields_dict.index_fields.grid.refresh();
		},
	});
}
