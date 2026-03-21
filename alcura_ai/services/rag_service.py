"""Retrieval-Augmented Generation service backed by Qdrant.

Handles embedding generation (via OpenAI), vector upsert/delete, and
similarity search against an on-prem Qdrant instance. All Qdrant
settings are read from Alcura AI Settings at call time.
"""

import json
import time
import uuid

import frappe
from qdrant_client import QdrantClient
from qdrant_client.models import (
	Distance,
	FieldCondition,
	Filter,
	MatchValue,
	PointStruct,
	VectorParams,
)

from alcura_ai.services.openai_service import get_client as get_openai_client

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_PAYLOAD_TEXT = 1500


def _get_logger():
	return frappe.logger("alcura_ai", allow_site=True)


def _get_rag_settings():
	"""Return RAG-related settings; throw if RAG is not enabled."""
	settings = frappe.get_single("Alcura AI Settings")
	if not settings.enable_rag:
		frappe.throw("RAG is not enabled. Enable it in Alcura AI Settings.")
	return settings


def get_qdrant_client(settings=None):
	"""Build a QdrantClient from stored settings."""
	settings = settings or _get_rag_settings()
	api_key = settings.get_password("qdrant_api_key") if settings.qdrant_api_key else None
	return QdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=30)


def ensure_collection(settings=None):
	"""Create the Qdrant collection if it does not already exist."""
	settings = settings or _get_rag_settings()
	client = get_qdrant_client(settings)
	collection = settings.qdrant_collection
	dim = settings.qdrant_vector_size or 1536

	existing = [c.name for c in client.get_collections().collections]
	if collection not in existing:
		client.create_collection(
			collection_name=collection,
			vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
		)
		_get_logger().info(f"Created Qdrant collection '{collection}' (dim={dim})")


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def embed_texts(texts, settings=None):
	"""Embed a batch of texts via OpenAI Embeddings API.

	Returns list of float-vectors, one per input text.
	"""
	settings = settings or _get_rag_settings()
	model = settings.embedding_model or "text-embedding-3-small"
	dim = settings.qdrant_vector_size or 1536

	openai = get_openai_client()

	kwargs = {"model": model, "input": texts}
	if dim and model.startswith("text-embedding-3"):
		kwargs["dimensions"] = dim

	response = openai.embeddings.create(**kwargs)
	return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
	"""Split text into overlapping chunks by character count.

	Returns list of dicts: [{text, chunk_index}, ...].
	"""
	if not text or not text.strip():
		return []

	chunks = []
	start = 0
	idx = 0
	while start < len(text):
		end = start + chunk_size
		chunk = text[start:end]
		if chunk.strip():
			chunks.append({"text": chunk.strip(), "chunk_index": idx})
			idx += 1
		start += chunk_size - overlap

	return chunks


# ---------------------------------------------------------------------------
# Ingest (upsert) / delete
# ---------------------------------------------------------------------------


def upsert_chunks(source_name, chunks_with_text, settings=None):
	"""Embed and upsert chunks into Qdrant for a given knowledge source.

	Args:
		source_name: Frappe document name of the Alcura Knowledge Source.
		chunks_with_text: list of {text, chunk_index} dicts.
		settings: optional pre-fetched settings.

	Returns:
		Number of points upserted.
	"""
	if not chunks_with_text:
		return 0

	settings = settings or _get_rag_settings()
	logger = _get_logger()

	ensure_collection(settings)

	texts = [c["text"] for c in chunks_with_text]
	vectors = embed_texts(texts, settings)

	client = get_qdrant_client(settings)
	collection = settings.qdrant_collection

	points = []
	for chunk, vector in zip(chunks_with_text, vectors):
		point_id = str(uuid.uuid4())
		payload = {
			"source_id": source_name,
			"chunk_index": chunk["chunk_index"],
			"text": chunk["text"][:MAX_PAYLOAD_TEXT],
		}
		points.append(PointStruct(id=point_id, vector=vector, payload=payload))

	batch_size = 100
	for i in range(0, len(points), batch_size):
		client.upsert(collection_name=collection, points=points[i : i + batch_size])

	logger.info(f"Upserted {len(points)} points for source '{source_name}'")
	return len(points)


def delete_source(source_name, settings=None):
	"""Remove all Qdrant points belonging to a knowledge source."""
	settings = settings or _get_rag_settings()
	client = get_qdrant_client(settings)
	collection = settings.qdrant_collection

	client.delete(
		collection_name=collection,
		points_selector=Filter(
			must=[FieldCondition(key="source_id", match=MatchValue(value=source_name))]
		),
	)
	_get_logger().info(f"Deleted points for source '{source_name}' from Qdrant")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(query, top_k=None, source_filter=None, settings=None):
	"""Semantic search over the knowledge corpus.

	Args:
		query: Natural-language search query.
		top_k: Number of results (defaults to settings.rag_top_k).
		source_filter: Optional source_id to restrict results.
		settings: optional pre-fetched settings.

	Returns:
		list of {text, score, source_id, chunk_index}.
	"""
	settings = settings or _get_rag_settings()
	logger = _get_logger()

	top_k = top_k or settings.rag_top_k or 5
	collection = settings.qdrant_collection

	start = time.monotonic()
	query_vector = embed_texts([query], settings)[0]

	qdrant_filter = None
	if source_filter:
		qdrant_filter = Filter(
			must=[FieldCondition(key="source_id", match=MatchValue(value=source_filter))]
		)

	client = get_qdrant_client(settings)
	results = client.query_points(
		collection_name=collection,
		query=query_vector,
		query_filter=qdrant_filter,
		limit=top_k,
		with_payload=True,
	)

	elapsed_ms = (time.monotonic() - start) * 1000
	logger.info(f"RAG search: {len(results.points)} hits in {elapsed_ms:.0f}ms for query '{query[:80]}'")

	hits = []
	for point in results.points:
		payload = point.payload or {}
		hits.append({
			"text": payload.get("text", ""),
			"score": round(point.score, 4),
			"source_id": payload.get("source_id", ""),
			"chunk_index": payload.get("chunk_index", 0),
		})

	return hits


def format_tool_result(hits):
	"""Format search hits as a JSON string suitable for the tool response."""
	if not hits:
		return json.dumps({"results": [], "message": "No relevant knowledge found."})

	trimmed = []
	for h in hits:
		trimmed.append({
			"text": h["text"][:MAX_PAYLOAD_TEXT],
			"score": h["score"],
			"source": h["source_id"],
		})

	return json.dumps({"results": trimmed}, default=str)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def health_check():
	"""Verify Qdrant is reachable and the collection exists.

	Returns dict with status info; raises on hard failure.
	"""
	settings = _get_rag_settings()
	client = get_qdrant_client(settings)
	collection = settings.qdrant_collection

	collections = [c.name for c in client.get_collections().collections]
	exists = collection in collections

	info = {
		"qdrant_reachable": True,
		"collection_exists": exists,
		"collection_name": collection,
	}

	if exists:
		col_info = client.get_collection(collection)
		info["points_count"] = col_info.points_count
		info["vector_size"] = col_info.config.params.vectors.size

	return info
