import frappe
from frappe.model.document import Document


class AlcuraAISettings(Document):

	def validate(self):
		if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
			frappe.throw("Temperature must be between 0 and 2.")

		if self.max_tokens is not None and self.max_tokens < 1:
			frappe.throw("Max Tokens must be at least 1.")

		if self.enable_rag:
			if not self.qdrant_url:
				frappe.throw("Qdrant URL is required when RAG is enabled.")
			if not self.qdrant_collection:
				frappe.throw("Qdrant Collection name is required when RAG is enabled.")
			if not self.qdrant_vector_size or self.qdrant_vector_size < 1:
				frappe.throw("Vector Size must be a positive integer matching your embedding model.")

		if self.max_tool_iterations is not None and self.max_tool_iterations < 1:
			frappe.throw("Max Tool Iterations must be at least 1.")
