# src/broll/search.py
"""
Hybrid search combining FTS5 keyword search and sqlite-vec semantic search
using Reciprocal Rank Fusion (RRF) for result merging.
"""
from __future__ import annotations

from .db import Database
from .embeddings import generate_embedding


# RRF constant - controls how much weight is given to rank position.
# Higher values flatten the ranking differences. 60 is standard.
RRF_K = 60


def hybrid_search(
    query: str | None,
    db: Database,
    limit: int = 10,
    fts_weight: float = 1.0,
    vec_weight: float = 1.0,
    filters: dict | None = None,
) -> list[dict]:
    """
    Perform hybrid search combining keyword (FTS5) and semantic (vector) results.

    Uses Reciprocal Rank Fusion to merge rankings from both methods.
    Each video gets a score of: weight * (1 / (RRF_K + rank))
    Final results are sorted by combined score.

    Args:
        query: The search query string. If None/empty, only filters are used.
        db: Database connection.
        limit: Max number of results to return.
        fts_weight: Weight multiplier for keyword search results.
        vec_weight: Weight multiplier for semantic search results.
        filters: Optional dict of structured filters (see db.build_filtered_query)

    Returns:
        List of video dicts, sorted by relevance, with a 'search_score' field.
    """
    # How many candidates to fetch from each method before fusing
    candidate_pool = limit * 3

    # ── Structured filters (if provided) ──
    filter_ids: set[int] | None = None
    if filters:
        filter_ids = set(db.get_filtered_ids(filters, limit=candidate_pool * 2))
        if not filter_ids:
            return []  # No videos match the filters

    # ── FTS5 keyword search ──
    if query:
        fts_results = _fts_search(query, db, candidate_pool)
    else:
        fts_results = []

    # ── Semantic vector search ──
    if query:
        vec_results = _vector_search(query, db, candidate_pool)
    else:
        vec_results = []

    # ── Handle filters-only search (no text query) ──
    if not query:
        if filter_ids:
            # Return filtered videos without scoring
            videos = db.get_videos_by_ids(list(filter_ids)[:limit])
            for video in videos:
                video["search_score"] = 1.0
                video["in_fts"] = False
                video["in_vec"] = False
            return videos
        return []

    # ── Reciprocal Rank Fusion ──
    scores: dict[int, float] = {}

    for rank, result in enumerate(fts_results):
        vid = result["video_id"]
        scores[vid] = scores.get(vid, 0.0) + fts_weight * (1.0 / (RRF_K + rank + 1))

    for rank, result in enumerate(vec_results):
        vid = result["video_id"]
        scores[vid] = scores.get(vid, 0.0) + vec_weight * (1.0 / (RRF_K + rank + 1))

    # ── Apply filters to search results ──
    if filter_ids and scores:
        scores = {vid: score for vid, score in scores.items() if vid in filter_ids}

    if not scores:
        return []

    # Sort by combined score (highest first) and take top N
    ranked_ids = sorted(scores.keys(), key=lambda vid: scores[vid], reverse=True)[:limit]

    # Fetch full video records
    videos = db.get_videos_by_ids(ranked_ids)

    # Attach search metadata
    for video in videos:
        vid = video["id"]
        video["search_score"] = round(scores[vid], 6)
        video["in_fts"] = any(r["video_id"] == vid for r in fts_results)
        video["in_vec"] = any(r["video_id"] == vid for r in vec_results)

    return videos



def keyword_search(query: str | None, db: Database, limit: int = 10, filters: dict | None = None) -> list[dict]:
    """FTS5-only keyword search with optional filters."""
    # ── Structured filters (if provided) ──
    filter_ids: set[int] | None = None
    if filters:
        filter_ids = set(db.get_filtered_ids(filters, limit=limit * 2))

    # ── Handle filters-only search (no text query) ──
    if not query:
        if filter_ids:
            videos = db.get_videos_by_ids(list(filter_ids)[:limit])
            for video in videos:
                video["search_score"] = 1.0
                video["in_fts"] = False
                video["in_vec"] = False
            return videos
        return []

    # ── FTS5 search ──
    results = _fts_search(query, db, limit * 2)
    if not results:
        return []

    # Apply filters to FTS results
    if filter_ids:
        results = [r for r in results if r["video_id"] in filter_ids]
        if not results:
            return []

    # Limit after filtering
    results = results[:limit]
    video_ids = [r["video_id"] for r in results]
    videos = db.get_videos_by_ids(video_ids)
    for i, video in enumerate(videos):
        video["search_score"] = abs(results[i]["rank"]) if i < len(results) else 0
        video["in_fts"] = True
        video["in_vec"] = False
    return videos


def semantic_search(query: str | None, db: Database, limit: int = 10, filters: dict | None = None) -> list[dict]:
    """Vector-only semantic search with optional filters."""
    # ── Structured filters (if provided) ──
    filter_ids: set[int] | None = None
    if filters:
        filter_ids = set(db.get_filtered_ids(filters, limit=limit * 2))

    # ── Handle filters-only search (no text query) ──
    if not query:
        if filter_ids:
            videos = db.get_videos_by_ids(list(filter_ids)[:limit])
            for video in videos:
                video["search_score"] = 1.0
                video["in_fts"] = False
                video["in_vec"] = True
            return videos
        return []

    # ── Vector search ──
    results = _vector_search(query, db, limit * 2)
    if not results:
        return []

    # Apply filters to vector results
    if filter_ids:
        results = [r for r in results if r["video_id"] in filter_ids]
        if not results:
            return []

    # Limit after filtering
    results = results[:limit]
    video_ids = [r["video_id"] for r in results]
    videos = db.get_videos_by_ids(video_ids)
    for i, video in enumerate(videos):
        video["search_score"] = results[i]["distance"] if i < len(results) else 0
        video["in_fts"] = False
        video["in_vec"] = True
    return videos


def _fts_search(query: str, db: Database, limit: int) -> list[dict]:
    """
    Run FTS5 search, handling query syntax gracefully.

    Tries the raw query first. If FTS5 rejects it (special characters, etc.),
    falls back to quoting each term individually.
    """
    results = db.search_fts(query, limit)
    if results:
        return results

    # Fallback: wrap each word in quotes so FTS5 treats them as plain terms
    terms = query.split()
    if len(terms) > 1:
        quoted = " OR ".join(f'"{term}"' for term in terms if term.strip())
        results = db.search_fts(quoted, limit)

    return results


def _vector_search(query: str, db: Database, limit: int) -> list[dict]:
    """
    Generate an embedding for the query and search the vector index.
    Returns empty list if embedding generation fails.
    """
    try:
        query_embedding = generate_embedding(query)
        rows = db.vector_search(query_embedding, limit)
        return [{"video_id": vid, "distance": dist} for vid, dist in rows]
    except Exception as e:
        print(f"  Warning: Vector search failed: {e}")
        return []

