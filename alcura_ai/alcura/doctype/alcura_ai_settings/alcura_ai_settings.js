frappe.ui.form.on("Alcura AI Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frm.events.test_connection(frm);
		});

		frm.add_custom_button(__("Open AI Chat"), () => {
			frappe.set_route("alcura-ai-chat");
		});
	},

	test_connection(frm) {
		if (!frm.doc.api_key) {
			frappe.msgprint(__("Please enter an API key first."));
			return;
		}

		frappe.call({
			method: "alcura_ai.api.v1.settings.test_openai_connection",
			freeze: true,
			freeze_message: __("Testing OpenAI connection..."),
			callback(r) {
				if (r.message && r.message.success) {
					frappe.msgprint({
						title: __("Connection Successful"),
						message: __("Connected to OpenAI. Model: {0}", [r.message.model]),
						indicator: "green",
					});
				}
			},
		});
	},
});
