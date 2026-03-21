import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AlcuraKnowledgeSource(Document):

	def validate(self):
		if self.source_type == "File" and not self.attachment:
			frappe.throw("Please attach a file for File-type sources.")
		if self.source_type == "URL" and not self.source_url:
			frappe.throw("Please provide a URL for URL-type sources.")

	def on_trash(self):
		settings = frappe.get_single("Alcura AI Settings")
		if settings.enable_rag:
			try:
				from alcura_ai.services.rag_service import delete_source
				delete_source(self.name)
			except Exception as e:
				frappe.logger("alcura_ai", allow_site=True).warning(
					f"Failed to delete vectors for '{self.name}': {e}"
				)

	@frappe.whitelist()
	def build_index(self):
		"""Chunk the source content and upsert embeddings into Qdrant."""
		settings = frappe.get_single("Alcura AI Settings")
		if not settings.enable_rag:
			frappe.throw("RAG is not enabled. Enable it in Alcura AI Settings.")

		text = self._extract_text()
		if not text or not text.strip():
			frappe.throw("No content to index. Add content or attach a file first.")

		from alcura_ai.services.rag_service import chunk_text, delete_source, upsert_chunks

		delete_source(self.name, settings)

		chunks = chunk_text(text)
		if not chunks:
			frappe.throw("Content produced no indexable chunks.")

		count = upsert_chunks(self.name, chunks, settings)

		self.db_set("chunk_count", count, update_modified=False)
		self.db_set("last_indexed", now_datetime(), update_modified=False)
		self.db_set("content", text, update_modified=False)
		frappe.msgprint(f"Indexed {count} chunks into Qdrant.", indicator="green", alert=True)

	@frappe.whitelist()
	def clear_index(self):
		"""Remove all vectors for this source from Qdrant."""
		settings = frappe.get_single("Alcura AI Settings")
		if not settings.enable_rag:
			frappe.throw("RAG is not enabled.")

		from alcura_ai.services.rag_service import delete_source

		delete_source(self.name, settings)
		self.db_set("chunk_count", 0, update_modified=False)
		self.db_set("last_indexed", None, update_modified=False)
		frappe.msgprint("Index cleared.", indicator="orange", alert=True)

	def _extract_text(self):
		"""Return the raw text for this source."""
		if self.source_type == "Manual":
			return self.content or ""

		if self.source_type == "File" and self.attachment:
			return self._read_file_attachment()

		if self.source_type == "URL" and self.source_url:
			return self._fetch_url()

		return ""

	def _read_file_attachment(self):
		"""Read text from an attached file (txt, md, csv, or pdf placeholder)."""
		file_doc = frappe.get_doc("File", {"file_url": self.attachment})
		file_path = file_doc.get_full_path()

		if file_path.endswith(".pdf"):
			frappe.throw("PDF parsing is not yet supported. Paste the text content manually.")

		with open(file_path, encoding="utf-8", errors="replace") as f:
			return f.read()

	def _fetch_url(self):
		"""Placeholder for URL fetching — to be extended."""
		frappe.throw(
			"Automatic URL fetching is not yet implemented. "
			"Copy the page content into the Content field instead."
		)
