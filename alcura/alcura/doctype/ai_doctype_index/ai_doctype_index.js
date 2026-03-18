frappe.ui.form.on("AI DocType Index", {
	refresh(frm) {
		if (frm.doc.reference_doctype) {
			frm.add_custom_button(__("Populate Fields"), () => {
				frm.call("populate_fields").then(() => {
					frm.dirty();
					frm.refresh_fields();
					frappe.show_alert({
						message: __("Fields populated from {0}", [frm.doc.reference_doctype]),
						indicator: "green",
					});
				});
			});
		}
	},

	reference_doctype(frm) {
		if (frm.doc.reference_doctype && !frm.doc.index_fields?.length) {
			frm.call("populate_fields").then(() => {
				frm.dirty();
				frm.refresh_fields();
			});
		}
	},
});
