frappe.ui.form.on("Alcura Knowledge Source", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Build Index"), () => {
				frm.events.build_index(frm);
			}, __("Actions"));

			frm.add_custom_button(__("Clear Index"), () => {
				frm.events.clear_index(frm);
			}, __("Actions"));
		}
	},

	build_index(frm) {
		frappe.call({
			doc: frm.doc,
			method: "build_index",
			freeze: true,
			freeze_message: __("Chunking and embedding..."),
			callback() {
				frm.reload_doc();
			},
		});
	},

	clear_index(frm) {
		frappe.confirm(
			__("Remove all indexed vectors for this source?"),
			() => {
				frappe.call({
					doc: frm.doc,
					method: "clear_index",
					freeze: true,
					freeze_message: __("Clearing index..."),
					callback() {
						frm.reload_doc();
					},
				});
			}
		);
	},
});
