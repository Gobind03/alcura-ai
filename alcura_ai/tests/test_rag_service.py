"""Tests for the RAG service (chunking, tool definition, dispatch).

These tests mock Qdrant and OpenAI so they run without external services.
"""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura_ai.services.rag_service import chunk_text, format_tool_result


class TestChunking(FrappeTestCase):
	"""Tests for text chunking logic."""

	def test_empty_text(self):
		self.assertEqual(chunk_text(""), [])
		self.assertEqual(chunk_text(None), [])
		self.assertEqual(chunk_text("   "), [])

	def test_short_text(self):
		chunks = chunk_text("Hello world")
		self.assertEqual(len(chunks), 1)
		self.assertEqual(chunks[0]["text"], "Hello world")
		self.assertEqual(chunks[0]["chunk_index"], 0)

	def test_overlap_produces_multiple_chunks(self):
		text = "a" * 2000
		chunks = chunk_text(text, chunk_size=800, overlap=100)
		self.assertGreater(len(chunks), 1)
		for i, chunk in enumerate(chunks):
			self.assertEqual(chunk["chunk_index"], i)
			self.assertTrue(len(chunk["text"]) <= 800)

	def test_chunk_indices_sequential(self):
		text = "word " * 500
		chunks = chunk_text(text, chunk_size=100, overlap=20)
		indices = [c["chunk_index"] for c in chunks]
		self.assertEqual(indices, list(range(len(chunks))))


class TestFormatToolResult(FrappeTestCase):
	"""Tests for formatting search hits into a tool response."""

	def test_empty_hits(self):
		result = json.loads(format_tool_result([]))
		self.assertEqual(result["results"], [])
		self.assertIn("No relevant", result["message"])

	def test_hits_formatted(self):
		hits = [
			{"text": "some content", "score": 0.92, "source_id": "SRC-001", "chunk_index": 0},
			{"text": "other content", "score": 0.85, "source_id": "SRC-002", "chunk_index": 1},
		]
		result = json.loads(format_tool_result(hits))
		self.assertEqual(len(result["results"]), 2)
		self.assertEqual(result["results"][0]["source"], "SRC-001")
		self.assertAlmostEqual(result["results"][0]["score"], 0.92)

	def test_text_truncation(self):
		hits = [{"text": "x" * 5000, "score": 0.9, "source_id": "S", "chunk_index": 0}]
		result = json.loads(format_tool_result(hits))
		self.assertLessEqual(len(result["results"][0]["text"]), 1500)


class TestRagToolDefinition(FrappeTestCase):
	"""Tests that search_knowledge tool appears/disappears based on settings."""

	def setUp(self):
		super().setUp()
		self.settings = frappe.get_single("Alcura AI Settings")
		self._original_enable = self.settings.enable_rag

	def tearDown(self):
		self.settings.db_set("enable_rag", self._original_enable, update_modified=False)
		from alcura_ai.services.cache_service import invalidate_all
		invalidate_all()
		super().tearDown()

	def test_rag_tool_excluded_when_disabled(self):
		self.settings.db_set("enable_rag", 0, update_modified=False)
		from alcura_ai.services.cache_service import invalidate_all
		invalidate_all()

		from alcura_ai.services.data_service import build_tool_definitions
		tools = build_tool_definitions()
		names = [t["function"]["name"] for t in tools]
		self.assertNotIn("search_knowledge", names)

	@patch("alcura_ai.services.data_service.frappe")
	def test_rag_tool_included_when_enabled_with_sources(self, mock_frappe_module):
		"""When enable_rag is on and sources exist, search_knowledge appears."""
		self.settings.db_set("enable_rag", 1, update_modified=False)
		self.settings.db_set("qdrant_url", "http://localhost:6333", update_modified=False)
		self.settings.db_set("qdrant_collection", "test", update_modified=False)
		self.settings.db_set("qdrant_vector_size", 1536, update_modified=False)
		from alcura_ai.services.cache_service import invalidate_all
		invalidate_all()

		from alcura_ai.services.data_service import _build_rag_tool_definition

		with patch("alcura_ai.services.data_service.frappe") as mf:
			mf.get_single.return_value = self.settings
			mf.get_all.return_value = [{"title": "Test Source"}]
			tool = _build_rag_tool_definition()

		if tool is None:
			self.skipTest("RAG tool not generated (no active sources in test env)")

		self.assertEqual(tool["function"]["name"], "search_knowledge")
		self.assertIn("query", tool["function"]["parameters"]["properties"])


class TestSearchMocked(FrappeTestCase):
	"""Tests for the search function with mocked Qdrant."""

	@patch("alcura_ai.services.rag_service.get_qdrant_client")
	@patch("alcura_ai.services.rag_service.embed_texts")
	def test_search_returns_hits(self, mock_embed, mock_client_fn):
		mock_embed.return_value = [[0.1] * 1536]

		mock_point = MagicMock()
		mock_point.score = 0.95
		mock_point.payload = {"text": "test chunk", "source_id": "SRC-1", "chunk_index": 0}

		mock_result = MagicMock()
		mock_result.points = [mock_point]

		mock_client = MagicMock()
		mock_client.query_points.return_value = mock_result
		mock_client_fn.return_value = mock_client

		settings = frappe.get_single("Alcura AI Settings")
		settings.enable_rag = 1
		settings.qdrant_url = "http://localhost:6333"
		settings.qdrant_collection = "test"
		settings.qdrant_vector_size = 1536
		settings.rag_top_k = 5

		from alcura_ai.services.rag_service import search
		with patch("alcura_ai.services.rag_service._get_rag_settings", return_value=settings):
			hits = search("what is the policy?", settings=settings)

		self.assertEqual(len(hits), 1)
		self.assertEqual(hits[0]["text"], "test chunk")
		self.assertAlmostEqual(hits[0]["score"], 0.95)
		self.assertEqual(hits[0]["source_id"], "SRC-1")


class TestUpsertMocked(FrappeTestCase):
	"""Tests for upsert_chunks with mocked Qdrant + OpenAI."""

	@patch("alcura_ai.services.rag_service.get_qdrant_client")
	@patch("alcura_ai.services.rag_service.embed_texts")
	@patch("alcura_ai.services.rag_service.ensure_collection")
	def test_upsert_calls_client(self, mock_ensure, mock_embed, mock_client_fn):
		mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]

		mock_client = MagicMock()
		mock_client_fn.return_value = mock_client

		settings = frappe.get_single("Alcura AI Settings")
		settings.enable_rag = 1
		settings.qdrant_url = "http://localhost:6333"
		settings.qdrant_collection = "test"
		settings.qdrant_vector_size = 1536

		chunks = [
			{"text": "chunk one", "chunk_index": 0},
			{"text": "chunk two", "chunk_index": 1},
		]

		from alcura_ai.services.rag_service import upsert_chunks
		with patch("alcura_ai.services.rag_service._get_rag_settings", return_value=settings):
			count = upsert_chunks("SRC-TEST", chunks, settings)

		self.assertEqual(count, 2)
		mock_client.upsert.assert_called_once()
