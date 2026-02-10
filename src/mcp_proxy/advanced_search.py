"""
Advanced search and navigation processors for tool outputs.

Implements sophisticated search beyond simple grep:
- BM25 ranking for relevance-based search
- Fuzzy matching for approximate searches
- Context extraction around matches
- Structure navigation without loading full content
- Progressive refinement helpers

Each search backend can be used standalone or as part of the
processor pipeline via the ``BaseProcessor`` interface.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from mcp.types import Content, TextContent

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# BM25 ranking
# ---------------------------------------------------------------------------

class BM25Processor:
    """
    BM25 (Best Match 25) ranking for text search.

    Ranks text chunks by relevance to a search query, not just presence.
    Returns the top-K most relevant chunks instead of all matches.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        # Cache document-frequency computations across calls when the
        # corpus does not change.
        self._df_cache_key: Optional[int] = None
        self._df_cache: Dict[str, int] = {}

    def rank_chunks(
        self,
        text: str,
        query: str,
        chunk_size: int = 500,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rank text chunks by BM25 relevance to *query*."""
        chunks = self._create_chunks(text, chunk_size)
        if not chunks:
            return []

        query_terms = self._tokenize(query.lower())
        doc_count = len(chunks)
        avg_len = sum(len(c) for c in chunks) / doc_count

        # Compute IDF only once per unique corpus
        corpus_key = hash((tuple(chunks), tuple(query_terms)))
        if corpus_key != self._df_cache_key:
            # Pre-tokenize all chunks once
            chunk_token_sets = [set(self._tokenize(c.lower())) for c in chunks]
            self._df_cache = {
                term: sum(1 for ts in chunk_token_sets if term in ts)
                for term in query_terms
            }
            self._df_cache_key = corpus_key

        scored_chunks: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            score = self._calculate_bm25_score(
                chunk, query_terms, self._df_cache, doc_count, avg_len
            )
            if score > 0:
                scored_chunks.append(
                    {
                        "chunk": chunk,
                        "score": score,
                        "index": idx,
                        "start": idx * chunk_size,
                        "end": min((idx + 1) * chunk_size, len(text)),
                    }
                )

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

    # -- helpers -----------------------------------------------------------

    def _create_chunks(self, text: str, chunk_size: int) -> List[str]:
        overlap = chunk_size // 4
        chunks: List[str] = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i : i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _calculate_bm25_score(
        self,
        chunk: str,
        query_terms: List[str],
        term_doc_freq: Dict[str, int],
        doc_count: int,
        avg_doc_len: float,
    ) -> float:
        score = 0.0
        chunk_tokens = self._tokenize(chunk)
        chunk_len = len(chunk_tokens)
        term_freq = Counter(chunk_tokens)

        for term in query_terms:
            tf = term_freq.get(term, 0)
            if tf == 0:
                continue
            df = term_doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log((doc_count - df + 0.5) / (df + 0.5) + 1.0)
            score += idf * (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * chunk_len / avg_doc_len)
            )
        return score


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

class FuzzyMatcher:
    """
    Fuzzy string matching for approximate searches.

    Uses Levenshtein distance with early-termination optimisations.
    """

    @staticmethod
    def fuzzy_search(
        text: str,
        pattern: str,
        threshold: float = 0.7,
        max_matches: int = 10,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        pattern_len = len(pattern)
        text_len = len(text)

        # Early termination: minimum possible distance for a window
        max_allowed_distance = int((1.0 - threshold) * max(pattern_len, 1))

        skip_until = -1
        for i in range(text_len - pattern_len + 1):
            if i < skip_until:
                continue

            window = text[i : i + pattern_len]

            # Quick character-count pre-check
            if not FuzzyMatcher._quick_similarity_check(pattern, window, max_allowed_distance):
                continue

            similarity = FuzzyMatcher._similarity(pattern, window)
            if similarity >= threshold:
                context_start = max(0, i - 50)
                context_end = min(text_len, i + pattern_len + 50)
                matches.append(
                    {
                        "match": window,
                        "similarity": similarity,
                        "position": i,
                        "context": text[context_start:context_end],
                    }
                )
                # Skip ahead past the current match to avoid overlapping hits
                skip_until = i + pattern_len
                if len(matches) >= max_matches:
                    break

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches

    @staticmethod
    def _quick_similarity_check(s1: str, s2: str, max_distance: int) -> bool:
        """Cheap character-frequency pre-filter."""
        c1 = Counter(s1.lower())
        c2 = Counter(s2.lower())
        diff = sum((c1 - c2).values()) + sum((c2 - c1).values())
        return diff <= max_distance * 2

    @staticmethod
    def _similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        distance = FuzzyMatcher._levenshtein_distance(s1.lower(), s2.lower())
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return FuzzyMatcher._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]


# ---------------------------------------------------------------------------
# Context extraction
# ---------------------------------------------------------------------------

class ContextExtractor:
    """
    Extract meaningful context around matches.

    Returns paragraphs, sections, or logical units instead of just
    matching lines.
    """

    @staticmethod
    def extract_with_context(
        text: str,
        pattern: str,
        context_type: str = "paragraph",
        max_matches: int = 5,
    ) -> List[Dict[str, Any]]:
        regex = re.compile(pattern, re.IGNORECASE)
        matches: List[Dict[str, Any]] = []

        if context_type == "paragraph":
            contexts = ContextExtractor._split_paragraphs(text)
        elif context_type == "section":
            contexts = ContextExtractor._split_sections(text)
        elif context_type == "sentence":
            contexts = ContextExtractor._split_sentences(text)
        else:
            contexts = [(line, i) for i, line in enumerate(text.split("\n"))]

        for context_text, context_id in contexts:
            if regex.search(context_text):
                matches.append(
                    {
                        "context": context_text,
                        "context_id": context_id,
                        "context_type": context_type,
                        "matches": len(regex.findall(context_text)),
                    }
                )
                if len(matches) >= max_matches:
                    break
        return matches

    @staticmethod
    def _split_paragraphs(text: str) -> List[Tuple[str, int]]:
        return [(p.strip(), i) for i, p in enumerate(text.split("\n\n")) if p.strip()]

    @staticmethod
    def _split_sections(text: str) -> List[Tuple[str, int]]:
        sections: List[Tuple[str, int]] = []
        current_section: List[str] = []
        section_id = 0
        for line in text.split("\n"):
            if line.startswith("#") or (line and line[0].isupper() and len(line) < 100):
                if current_section:
                    sections.append(("\n".join(current_section), section_id))
                    section_id += 1
                current_section = [line]
            else:
                current_section.append(line)
        if current_section:
            sections.append(("\n".join(current_section), section_id))
        return sections

    @staticmethod
    def _split_sentences(text: str) -> List[Tuple[str, int]]:
        sentences = re.split(r"[.!?]+\s+", text)
        return [(s.strip(), i) for i, s in enumerate(sentences) if s.strip()]


# ---------------------------------------------------------------------------
# Structure navigation
# ---------------------------------------------------------------------------

class StructureNavigator:
    """
    Navigate data structures without loading full content.

    Provides metadata about structure to help agents explore efficiently.
    """

    @staticmethod
    def get_structure_summary(data: Any, max_depth: int = 3) -> Dict[str, Any]:
        return {
            "type": StructureNavigator._get_type(data),
            "size": StructureNavigator._get_size(data),
            "keys": StructureNavigator._get_keys(data, max_depth),
            "sample": StructureNavigator._get_sample(data),
            "statistics": StructureNavigator._get_statistics(data),
        }

    @staticmethod
    def _get_type(data: Any) -> str:
        if isinstance(data, dict):
            return "object"
        elif isinstance(data, list):
            return "array"
        elif isinstance(data, str):
            return "string"
        elif isinstance(data, bool):
            return "boolean"
        elif isinstance(data, (int, float)):
            return "number"
        return "unknown"

    @staticmethod
    def _get_size(data: Any) -> Dict[str, int]:
        if isinstance(data, dict):
            return {
                "fields": len(data),
                "total_items": sum(StructureNavigator._count_items(v) for v in data.values()),
            }
        elif isinstance(data, list):
            return {
                "items": len(data),
                "total_items": sum(StructureNavigator._count_items(item) for item in data),
            }
        elif isinstance(data, str):
            return {"characters": len(data), "lines": len(data.split("\n"))}
        return {}

    @staticmethod
    def _count_items(data: Any) -> int:
        if isinstance(data, dict):
            return 1 + sum(StructureNavigator._count_items(v) for v in data.values())
        elif isinstance(data, list):
            return len(data)
        return 1

    @staticmethod
    def _get_keys(data: Any, max_depth: int) -> Any:
        if max_depth <= 0:
            return "..."
        if isinstance(data, dict):
            return {
                k: StructureNavigator._get_keys(data[k], max_depth - 1)
                for k in list(data.keys())[:10]
            }
        elif isinstance(data, list) and data:
            return [StructureNavigator._get_keys(data[0], max_depth - 1)]
        return StructureNavigator._get_type(data)

    @staticmethod
    def _get_sample(data: Any, max_items: int = 3) -> Any:
        if isinstance(data, dict):
            sample_keys = list(data.keys())[:max_items]
            return {k: StructureNavigator._get_sample(data[k], 1) for k in sample_keys}
        elif isinstance(data, list):
            return [StructureNavigator._get_sample(item, 1) for item in data[:max_items]]
        elif isinstance(data, str) and len(data) > 100:
            return data[:100] + "..."
        return data

    @staticmethod
    def _get_statistics(data: Any) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        if isinstance(data, list):
            stats["count"] = len(data)
            if data and isinstance(data[0], dict):
                stats["fields"] = list(data[0].keys())[:10]
        elif isinstance(data, dict):
            stats["field_count"] = len(data)
            stats["field_names"] = list(data.keys())[:20]
        elif isinstance(data, str):
            stats["length"] = len(data)
            stats["lines"] = len(data.split("\n"))
            stats["words"] = len(data.split())
        return stats


# ---------------------------------------------------------------------------
# Progressive refinement helper
# ---------------------------------------------------------------------------

class ProgressiveRefinementHelper:
    """Helper for multi-step progressive refinement of searches."""

    def __init__(self) -> None:
        self.search_history: List[Dict[str, Any]] = []
        self.cached_results: Dict[str, Any] = {}

    def suggest_next_step(
        self, current_results: Any, search_type: str
    ) -> Dict[str, Any]:
        suggestions: Dict[str, Any] = {
            "refinement_options": [],
            "statistics": {},
            "recommended_action": "",
        }

        if isinstance(current_results, list):
            result_count = len(current_results)
            suggestions["statistics"]["result_count"] = result_count

            if result_count == 0:
                suggestions["recommended_action"] = "broaden_search"
                suggestions["refinement_options"] = [
                    "Use fuzzy matching",
                    "Increase context window",
                    "Try BM25 ranking",
                    "Search in different field",
                ]
            elif result_count > 50:
                suggestions["recommended_action"] = "narrow_search"
                suggestions["refinement_options"] = [
                    "Add more specific terms",
                    "Use stricter matching",
                    "Filter by additional criteria",
                    "Increase relevance threshold",
                ]
            else:
                suggestions["recommended_action"] = "refine_further"
                suggestions["refinement_options"] = [
                    "Extract specific fields",
                    "Get more context",
                    "Rank by relevance",
                    "Group similar results",
                ]

        return suggestions
