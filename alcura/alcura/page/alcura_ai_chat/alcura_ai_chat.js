frappe.pages["alcura-ai-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Alcura AI Chat"),
		single_column: false,
	});

	page.main.html(get_page_html());

	const chat = new AlcuraAIChat(page);
	chat.init();
};

function get_page_html() {
	return `
		<div class="alcura-ai-chat-container">
			<div class="chat-main">
				<div class="chat-messages" id="chat-messages">
					<div class="chat-welcome" id="chat-welcome">
						<div class="welcome-icon">
							<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
								<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
							</svg>
						</div>
						<h3>${__("Ask a question about your data")}</h3>
						<p class="text-muted">${__("I can help you query, analyze, and understand the data in your configured DocTypes.")}</p>
					</div>
				</div>
				<div class="chat-input-area">
					<div class="chat-input-wrapper">
						<textarea
							id="chat-input"
							class="chat-input"
							placeholder="${__("Ask a question about your data...")}"
							rows="1"
						></textarea>
						<button id="chat-send-btn" class="btn btn-primary btn-send" title="${__("Send")}">
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<line x1="22" y1="2" x2="11" y2="13"/>
								<polygon points="22 2 15 22 11 13 2 9 22 2"/>
							</svg>
						</button>
					</div>
					<div class="chat-hint text-muted text-xs">
						${__("Press Enter to send, Shift+Enter for new line")}
					</div>
				</div>
			</div>
			<div class="chat-sidebar">
				<div class="sidebar-section">
					<div class="sidebar-header">
						<span class="sidebar-title">${__("Data Sources")}</span>
						<button id="btn-refresh-context" class="btn btn-xs btn-default" title="${__("Refresh")}">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="23 4 23 10 17 10"/>
								<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
							</svg>
						</button>
					</div>
					<div id="context-list" class="context-list">
						<div class="text-muted text-sm">${__("Loading...")}</div>
					</div>
				</div>
				<div class="sidebar-section">
					<button id="btn-new-chat" class="btn btn-default btn-sm btn-block">
						${__("New Conversation")}
					</button>
				</div>
				<div class="sidebar-section">
					<a href="/desk/alcura-ai-settings" class="btn btn-default btn-xs btn-block">
						${__("AI Settings")}
					</a>
				</div>
			</div>
		</div>
	`;
}

class AlcuraAIChat {
	constructor(page) {
		this.page = page;
		this.history = [];
		this.is_sending = false;
	}

	init() {
		this.bind_events();
		this.load_context();
		this.auto_resize_input();
	}

	bind_events() {
		const input = document.getElementById("chat-input");
		const send_btn = document.getElementById("chat-send-btn");

		input.addEventListener("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send_message();
			}
		});

		send_btn.addEventListener("click", () => this.send_message());

		document.getElementById("btn-new-chat").addEventListener("click", () => {
			this.new_conversation();
		});

		document.getElementById("btn-refresh-context").addEventListener("click", () => {
			this.load_context();
		});
	}

	auto_resize_input() {
		const input = document.getElementById("chat-input");
		input.addEventListener("input", () => {
			input.style.height = "auto";
			input.style.height = Math.min(input.scrollHeight, 150) + "px";
		});
	}

	load_context() {
		const list = document.getElementById("context-list");
		list.innerHTML = `<div class="text-muted text-sm">${__("Loading...")}</div>`;

		frappe.call({
			method: "alcura.api.v1.chat.get_context",
			callback: (r) => {
				if (r.message && r.message.doctypes) {
					this.render_context(r.message.doctypes);
				} else {
					list.innerHTML = `<div class="text-muted text-sm">${__("No data sources configured.")}</div>`;
				}
			},
			error: () => {
				list.innerHTML = `<div class="text-muted text-sm text-danger">${__("Failed to load data sources.")}</div>`;
			},
		});
	}

	render_context(doctypes) {
		const list = document.getElementById("context-list");
		if (!doctypes.length) {
			list.innerHTML = `
				<div class="text-muted text-sm">
					${__("No data sources configured.")}
					<a href="/desk/ai-doctype-index/new">${__("Add one")}</a>
				</div>`;
			return;
		}

		list.innerHTML = doctypes
			.map(
				(d) => `
			<div class="context-item">
				<div class="context-item-title">${frappe.utils.escape_html(d.doctype)}</div>
				<div class="context-item-desc text-muted text-xs">${frappe.utils.escape_html(d.description || "")}</div>
				<div class="context-item-meta text-muted text-xs">${d.field_count} ${__("fields")}</div>
			</div>
		`
			)
			.join("");
	}

	send_message() {
		const input = document.getElementById("chat-input");
		const message = input.value.trim();

		if (!message || this.is_sending) return;

		this.is_sending = true;
		input.value = "";
		input.style.height = "auto";

		this.hide_welcome();
		this.append_message("user", message);
		this.show_typing_indicator();
		this.set_send_disabled(true);

		frappe.call({
			method: "alcura.api.v1.chat.send_message",
			args: {
				message: message,
				history: JSON.stringify(this.history),
			},
			callback: (r) => {
				this.remove_typing_indicator();
				if (r.message && r.message.response) {
					this.append_message("assistant", r.message.response);
				} else {
					this.append_message(
						"assistant",
						__("Sorry, I could not generate a response. Please try again.")
					);
				}
				this.is_sending = false;
				this.set_send_disabled(false);
				input.focus();
			},
			error: () => {
				this.remove_typing_indicator();
				this.append_message(
					"assistant",
					__("An error occurred while processing your request. Please try again.")
				);
				this.is_sending = false;
				this.set_send_disabled(false);
				input.focus();
			},
		});
	}

	append_message(role, content) {
		this.history.push({ role, content });

		const messages_el = document.getElementById("chat-messages");
		const msg_div = document.createElement("div");
		msg_div.className = `chat-message chat-message-${role}`;

		const bubble = document.createElement("div");
		bubble.className = "chat-bubble";

		if (role === "assistant") {
			bubble.innerHTML = frappe.markdown(content);
		} else {
			bubble.textContent = content;
		}

		msg_div.appendChild(bubble);
		messages_el.appendChild(msg_div);
		messages_el.scrollTop = messages_el.scrollHeight;
	}

	show_typing_indicator() {
		const messages_el = document.getElementById("chat-messages");
		const indicator = document.createElement("div");
		indicator.id = "typing-indicator";
		indicator.className = "chat-message chat-message-assistant";
		indicator.innerHTML = `
			<div class="chat-bubble typing-indicator">
				<span class="dot"></span>
				<span class="dot"></span>
				<span class="dot"></span>
			</div>
		`;
		messages_el.appendChild(indicator);
		messages_el.scrollTop = messages_el.scrollHeight;
	}

	remove_typing_indicator() {
		const indicator = document.getElementById("typing-indicator");
		if (indicator) indicator.remove();
	}

	hide_welcome() {
		const welcome = document.getElementById("chat-welcome");
		if (welcome) welcome.style.display = "none";
	}

	set_send_disabled(disabled) {
		document.getElementById("chat-send-btn").disabled = disabled;
	}

	new_conversation() {
		this.history = [];
		const messages_el = document.getElementById("chat-messages");
		messages_el.innerHTML = "";

		const welcome = document.getElementById("chat-welcome");
		if (welcome) {
			welcome.style.display = "";
		} else {
			messages_el.innerHTML = `
				<div class="chat-welcome" id="chat-welcome">
					<div class="welcome-icon">
						<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
							<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
						</svg>
					</div>
					<h3>${__("Ask a question about your data")}</h3>
					<p class="text-muted">${__("I can help you query, analyze, and understand the data in your configured DocTypes.")}</p>
				</div>
			`;
		}

		document.getElementById("chat-input").focus();
	}
}
