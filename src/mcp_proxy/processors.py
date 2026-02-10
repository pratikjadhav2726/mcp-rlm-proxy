"""
Processors for field projection, grep operations, and composable pipelines.

Provides a ``BaseProcessor`` ABC, concrete ``ProjectionProcessor`` and
``GrepProcessor`` implementations, a ``ProcessorResult`` data class, and a
``ProcessorPipeline`` for composable multi-step processing.
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from mcp.types import Content, ImageContent, TextContent

from mcp_proxy.advanced_search import (
    BM25Processor,
    ContextExtractor,
    FuzzyMatcher,
    StructureNavigator,
)
from mcp_proxy.executor_manager import ExecutorManager
from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ProcessorResult:
    """Standardised output returned by every processor."""

    content: List[Content]
    original_size: int
    filtered_size: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def savings_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return ((self.original_size - self.filtered_size) / self.original_size) * 100


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseProcessor(ABC):
    """Common interface implemented by every processor."""

    name: str = "base"

    @abstractmethod
    def process(self, content: List[Content], spec: Dict[str, Any]) -> ProcessorResult:
        """
        Process *content* according to *spec* and return a ``ProcessorResult``.

        Args:
            content: MCP Content items to process.
            spec: Processor-specific parameters (e.g. fields, pattern …).

        Returns:
            A ``ProcessorResult`` containing the filtered content and metadata.
        """
    
    async def process_async(
        self, content: List[Content], spec: Dict[str, Any]
    ) -> ProcessorResult:
        """
        Async version of process. Default implementation calls sync version.
        
        Override in subclasses to provide async implementation.
        """
        # Default: run sync version in executor if available
        if hasattr(self, 'executor_manager') and self.executor_manager:
            from functools import partial
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.executor_manager.executor,
                partial(self.process, content, spec)
            )
        return self.process(content, spec)


# ---------------------------------------------------------------------------
# Projection processor
# ---------------------------------------------------------------------------

class ProjectionProcessor(BaseProcessor):
    """Handles field projection operations on tool responses."""

    name: str = "projection"

    def __init__(self, executor_manager: Optional[ExecutorManager] = None) -> None:
        """Initialize projection processor with optional executor manager."""
        self.executor_manager = executor_manager

    # -- BaseProcessor interface -------------------------------------------

    def process(self, content: List[Content], spec: Dict[str, Any]) -> ProcessorResult:
        mode = spec.get("mode", "include")
        fields = spec.get("fields", [])

        if mode not in ("include", "exclude", "view"):
            raise ValueError(
                f"Invalid projection mode: {mode}. Must be 'include', 'exclude', or 'view'"
            )
        if not fields and mode != "view":
            raise ValueError("Projection requires a non-empty 'fields' list")

        original_size = _measure_content(content)
        projected = self.project_content(content, spec)
        filtered_size = _measure_content(projected)

        return ProcessorResult(
            content=projected,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata={
                "applied": True,
                "mode": mode,
                "fields": fields,
            },
        )

    async def process_async(
        self, content: List[Content], spec: Dict[str, Any]
    ) -> ProcessorResult:
        """Async version that offloads JSON parsing and projection to thread pool."""
        mode = spec.get("mode", "include")
        fields = spec.get("fields", [])

        if mode not in ("include", "exclude", "view"):
            raise ValueError(
                f"Invalid projection mode: {mode}. Must be 'include', 'exclude', or 'view'"
            )
        if not fields and mode != "view":
            raise ValueError("Projection requires a non-empty 'fields' list")

        original_size = _measure_content(content)
        projected = await self.project_content_async(content, spec)
        filtered_size = _measure_content(projected)

        return ProcessorResult(
            content=projected,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata={
                "applied": True,
                "mode": mode,
                "fields": fields,
            },
        )

    # -- Public static helpers (kept for backward-compat) ------------------

    @staticmethod
    def apply_projection(
        data: Any, projection: Dict[str, Any], path: str = ""
    ) -> Any:
        """
        Apply field projection to *data* based on *projection* spec.

        Supports ``include``, ``exclude``, and ``view`` modes as well as
        nested dot-separated paths and array element projection.
        """
        mode = projection.get("mode", "include")
        fields = projection.get("fields", [])

        # Handle lists by applying projection to each item
        if isinstance(data, list):
            return [
                ProjectionProcessor.apply_projection(item, projection, path)
                for item in data
            ]

        # Handle dictionaries
        if not isinstance(data, dict):
            return data

        if mode == "include":
            return ProjectionProcessor._apply_include(data, fields, projection, path)
        elif mode == "exclude":
            return ProjectionProcessor._apply_exclude(data, fields, projection, path)
        elif mode == "view":
            view_fields = projection.get("view", fields[0] if fields else "default")  # noqa: F841
            return ProjectionProcessor.apply_projection(
                data, {"mode": "include", "fields": fields}
            )

        return data

    @staticmethod
    def project_content(
        content: List[Content], projection: Dict[str, Any]
    ) -> List[Content]:
        """Apply projection to MCP Content objects."""
        projected: List[Content] = []
        for item in content:
            if isinstance(item, TextContent):
                try:
                    data = json.loads(item.text)
                    if isinstance(data, (dict, list)):
                        projected_data = ProjectionProcessor.apply_projection(
                            data, projection
                        )
                        projected.append(
                            TextContent(
                                type="text",
                                text=json.dumps(projected_data, indent=2),
                            )
                        )
                    else:
                        projected.append(item)
                except json.JSONDecodeError:
                    projected.append(item)
            elif isinstance(item, ImageContent):
                projected.append(item)
            else:
                projected.append(item)
        return projected

    async def project_content_async(
        self, content: List[Content], projection: Dict[str, Any]
    ) -> List[Content]:
        """Async version that offloads JSON parsing and projection to thread pool."""
        projected: List[Content] = []
        
        for item in content:
            if isinstance(item, TextContent):
                try:
                    # Offload JSON parsing to thread pool
                    if self.executor_manager:
                        data = await self.executor_manager.run_cpu_bound(json.loads, item.text)
                    else:
                        data = json.loads(item.text)
                    
                    if isinstance(data, (dict, list)):
                        # Projection itself can be CPU-bound for large structures
                        if self.executor_manager:
                            projected_data = await self.executor_manager.run_cpu_bound(
                                self.apply_projection,
                                data,
                                projection
                            )
                            projected_text = await self.executor_manager.run_cpu_bound(
                                lambda d: json.dumps(d, indent=2),
                                projected_data
                            )
                        else:
                            projected_data = self.apply_projection(data, projection)
                            projected_text = json.dumps(projected_data, indent=2)
                        
                        projected.append(TextContent(type="text", text=projected_text))
                    else:
                        projected.append(item)
                except json.JSONDecodeError:
                    projected.append(item)
            elif isinstance(item, ImageContent):
                projected.append(item)
            else:
                projected.append(item)
        
        return projected

    # -- Internal helpers --------------------------------------------------

    @staticmethod
    def _apply_include(
        data: Dict[str, Any],
        fields: List[str],
        projection: Dict[str, Any],
        path: str,
    ) -> Dict[str, Any]:
        """Include-mode projection."""
        # Separate array projections from regular fields
        array_projections: Dict[str, List[str]] = {}
        regular_fields: List[str] = []

        for fld in fields:
            if "." in fld:
                parts = fld.split(".")
                parent_key = parts[0]
                nested_field = ".".join(parts[1:])
                if parent_key in data and isinstance(data[parent_key], list):
                    array_projections.setdefault(parent_key, []).append(nested_field)
                else:
                    regular_fields.append(fld)
            else:
                regular_fields.append(fld)

        result: Dict[str, Any] = {}

        # Array projections
        for parent_key, nested_fields in array_projections.items():
            if parent_key in data:
                nested_proj = {"mode": "include", "fields": nested_fields}
                result[parent_key] = ProjectionProcessor.apply_projection(
                    data[parent_key], nested_proj, parent_key
                )

        # Regular fields
        for fld in regular_fields:
            if fld in data:
                value = data[fld]
                if isinstance(value, (dict, list)):
                    result[fld] = ProjectionProcessor.apply_projection(
                        value, projection, f"{path}.{fld}" if path else fld
                    )
                else:
                    result[fld] = value
            elif "." in fld:
                parts = fld.split(".")
                current = data
                for part in parts[:-1]:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        break
                else:
                    if isinstance(current, dict) and parts[-1] in current:
                        nested = result
                        for part in parts[:-1]:
                            if part not in nested:
                                nested[part] = {}
                            nested = nested[part]
                        value = current[parts[-1]]
                        if isinstance(value, (dict, list)):
                            nested[parts[-1]] = ProjectionProcessor.apply_projection(
                                value, projection, fld
                            )
                        else:
                            nested[parts[-1]] = value

        return result

    @staticmethod
    def _apply_exclude(
        data: Dict[str, Any],
        fields: List[str],
        projection: Dict[str, Any],
        path: str,
    ) -> Dict[str, Any]:
        """Exclude-mode projection."""
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if key in fields:
                continue

            should_exclude_key = False
            nested_exclusions: List[str] = []
            for fld in fields:
                if fld == key:
                    should_exclude_key = True
                    break
                elif fld.startswith(f"{key}."):
                    nested_exclusions.append(fld[len(key) + 1:])

            if should_exclude_key:
                continue

            if nested_exclusions:
                nested_proj = {"mode": "exclude", "fields": nested_exclusions}
                if isinstance(value, (dict, list)):
                    result[key] = ProjectionProcessor.apply_projection(
                        value, nested_proj, f"{path}.{key}" if path else key
                    )
                else:
                    result[key] = value
            else:
                if isinstance(value, (dict, list)):
                    result[key] = ProjectionProcessor.apply_projection(
                        value, projection, f"{path}.{key}" if path else key
                    )
                else:
                    result[key] = value

        return result


# ---------------------------------------------------------------------------
# Grep processor
# ---------------------------------------------------------------------------

class GrepProcessor(BaseProcessor):
    """Handles advanced search operations on tool outputs.

    Supports modes: ``regex`` (default), ``bm25``, ``fuzzy``, ``context``,
    ``structure``.  Delegates to specialised sub-processors via a strategy
    map rather than an if/elif chain.
    """

    name: str = "grep"

    def __init__(self, executor_manager: Optional[ExecutorManager] = None) -> None:
        """Initialize grep processor with optional executor manager."""
        self.bm25 = BM25Processor()
        self.fuzzy = FuzzyMatcher()
        self.context_extractor = ContextExtractor()
        self.navigator = StructureNavigator()
        self.executor_manager = executor_manager

        # Strategy map – each value is a bound method
        self._strategies: Dict[str, Any] = {
            "regex": self._apply_regex_search,
            "bm25": self._apply_bm25_search,
            "fuzzy": self._apply_fuzzy_search,
            "context": self._apply_context_search,
            "structure": self._apply_structure_navigation,
        }
        
        # Async strategy map
        self._async_strategies: Dict[str, Any] = {
            "regex": self._apply_regex_search_async,
            "bm25": self._apply_bm25_search_async,
            "fuzzy": self._apply_fuzzy_search_async,
            "context": self._apply_context_search_async,
            "structure": self._apply_structure_navigation_async,
        }

    # -- BaseProcessor interface -------------------------------------------

    def process(self, content: List[Content], spec: Dict[str, Any]) -> ProcessorResult:
        original_size = _measure_content(content)
        filtered = self.apply_grep(content, spec)
        filtered_size = _measure_content(filtered)

        return ProcessorResult(
            content=filtered,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata={
                "applied": True,
                "mode": spec.get("mode", "regex"),
                "pattern": spec.get("pattern") or spec.get("query"),
            },
        )

    async def process_async(
        self, content: List[Content], spec: Dict[str, Any]
    ) -> ProcessorResult:
        """Async version that offloads CPU-bound work to thread pool."""
        original_size = _measure_content(content)
        filtered = await self.apply_grep_async(content, spec)
        filtered_size = _measure_content(filtered)

        return ProcessorResult(
            content=filtered,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata={
                "applied": True,
                "mode": spec.get("mode", "regex"),
                "pattern": spec.get("pattern") or spec.get("query"),
            },
        )

    # -- Public grep entry point -------------------------------------------

    def apply_grep(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Apply search to content with multiple modes.

        Unlike the previous static method this is a proper instance method
        that reuses the already-instantiated sub-processors.
        """
        search_mode = grep_spec.get("mode", "regex")
        handler = self._strategies.get(search_mode)
        if handler is None:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Unknown search mode '{search_mode}'. "
                    f"Supported: {', '.join(self._strategies)}",
                )
            ]
        return handler(content, grep_spec)

    async def apply_grep_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async version that offloads CPU-bound work to thread pool."""
        search_mode = grep_spec.get("mode", "regex")
        handler = self._async_strategies.get(search_mode)
        if handler is None:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Unknown search mode '{search_mode}'. "
                    f"Supported: {', '.join(self._async_strategies)}",
                )
            ]
        return await handler(content, grep_spec)

    # -- Strategy implementations ------------------------------------------

    def _apply_bm25_search(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        query = grep_spec.get("query") or grep_spec.get("pattern", "")
        top_k = grep_spec.get("topK", 5)
        chunk_size = grep_spec.get("chunkSize", 500)

        if not query:
            return [TextContent(type="text", text="Error: BM25 search requires 'query' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            text = item.text
            try:
                data = json.loads(text)
                text = json.dumps(data, indent=2)
            except json.JSONDecodeError:
                pass

            ranked_chunks = self.bm25.rank_chunks(text, query, chunk_size, top_k)
            if ranked_chunks:
                result_text = f"BM25 Search Results (query: '{query}', top {len(ranked_chunks)} of {top_k}):\n\n"
                for i, chunk_data in enumerate(ranked_chunks, 1):
                    result_text += f"=== Result {i} (Score: {chunk_data['score']:.4f}) ===\n"
                    result_text += f"{chunk_data['chunk']}\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No relevant results found.")]

    async def _apply_bm25_search_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async BM25 search that offloads CPU work to thread pool."""
        query = grep_spec.get("query") or grep_spec.get("pattern", "")
        top_k = grep_spec.get("topK", 5)
        chunk_size = grep_spec.get("chunkSize", 500)

        if not query:
            return [TextContent(type="text", text="Error: BM25 search requires 'query' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            
            text = item.text
            try:
                # Offload JSON parsing
                if self.executor_manager:
                    data = await self.executor_manager.run_cpu_bound(json.loads, text)
                    text = await self.executor_manager.run_cpu_bound(
                        lambda d: json.dumps(d, indent=2), data
                    )
                else:
                    data = json.loads(text)
                    text = json.dumps(data, indent=2)
            except json.JSONDecodeError:
                pass

            # Offload BM25 ranking to thread pool
            if self.executor_manager:
                ranked_chunks = await self.executor_manager.run_cpu_bound(
                    self.bm25.rank_chunks,
                    text,
                    query,
                    chunk_size,
                    top_k
                )
            else:
                ranked_chunks = self.bm25.rank_chunks(text, query, chunk_size, top_k)
            
            if ranked_chunks:
                result_text = f"BM25 Search Results (query: '{query}', top {len(ranked_chunks)} of {top_k}):\n\n"
                for i, chunk_data in enumerate(ranked_chunks, 1):
                    result_text += f"=== Result {i} (Score: {chunk_data['score']:.4f}) ===\n"
                    result_text += f"{chunk_data['chunk']}\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No relevant results found.")]

    def _apply_fuzzy_search(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        pattern = grep_spec.get("pattern", "")
        threshold = grep_spec.get("threshold", 0.7)
        max_matches = grep_spec.get("maxMatches", 10)

        if not pattern:
            return [TextContent(type="text", text="Error: Fuzzy search requires 'pattern' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            matches = self.fuzzy.fuzzy_search(item.text, pattern, threshold, max_matches)
            if matches:
                result_text = f"Fuzzy Search Results (pattern: '{pattern}', threshold: {threshold}):\n\n"
                for i, match in enumerate(matches, 1):
                    result_text += f"=== Match {i} (Similarity: {match['similarity']:.2%}) ===\n"
                    result_text += f"Found: \"{match['match']}\"\n"
                    result_text += f"Context: ...{match['context']}...\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No fuzzy matches found.")]

    async def _apply_fuzzy_search_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async fuzzy search that offloads CPU work to thread pool."""
        pattern = grep_spec.get("pattern", "")
        threshold = grep_spec.get("threshold", 0.7)
        max_matches = grep_spec.get("maxMatches", 10)

        if not pattern:
            return [TextContent(type="text", text="Error: Fuzzy search requires 'pattern' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            
            # Offload fuzzy matching to thread pool
            if self.executor_manager:
                matches = await self.executor_manager.run_cpu_bound(
                    self.fuzzy.fuzzy_search,
                    item.text,
                    pattern,
                    threshold,
                    max_matches
                )
            else:
                matches = self.fuzzy.fuzzy_search(item.text, pattern, threshold, max_matches)
            
            if matches:
                result_text = f"Fuzzy Search Results (pattern: '{pattern}', threshold: {threshold}):\n\n"
                for i, match in enumerate(matches, 1):
                    result_text += f"=== Match {i} (Similarity: {match['similarity']:.2%}) ===\n"
                    result_text += f"Found: \"{match['match']}\"\n"
                    result_text += f"Context: ...{match['context']}...\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No fuzzy matches found.")]

    def _apply_context_search(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        pattern = grep_spec.get("pattern", "")
        context_type = grep_spec.get("contextType", "paragraph")
        max_matches = grep_spec.get("maxMatches", 5)

        if not pattern:
            return [TextContent(type="text", text="Error: Context search requires 'pattern' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            matches = self.context_extractor.extract_with_context(
                item.text, pattern, context_type, max_matches
            )
            if matches:
                result_text = f"Context Search Results (pattern: '{pattern}', context: {context_type}):\n\n"
                for i, match in enumerate(matches, 1):
                    result_text += f"=== {context_type.capitalize()} {i} ({match['matches']} match(es)) ===\n"
                    result_text += f"{match['context']}\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No contextual matches found.")]

    async def _apply_context_search_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async context search that offloads CPU work to thread pool."""
        pattern = grep_spec.get("pattern", "")
        context_type = grep_spec.get("contextType", "paragraph")
        max_matches = grep_spec.get("maxMatches", 5)

        if not pattern:
            return [TextContent(type="text", text="Error: Context search requires 'pattern' parameter")]

        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            
            # Offload context extraction to thread pool
            if self.executor_manager:
                matches = await self.executor_manager.run_cpu_bound(
                    self.context_extractor.extract_with_context,
                    item.text,
                    pattern,
                    context_type,
                    max_matches
                )
            else:
                matches = self.context_extractor.extract_with_context(
                    item.text, pattern, context_type, max_matches
                )
            
            if matches:
                result_text = f"Context Search Results (pattern: '{pattern}', context: {context_type}):\n\n"
                for i, match in enumerate(matches, 1):
                    result_text += f"=== {context_type.capitalize()} {i} ({match['matches']} match(es)) ===\n"
                    result_text += f"{match['context']}\n\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No contextual matches found.")]

    def _apply_structure_navigation(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        max_depth = grep_spec.get("maxDepth", 3)
        results: List[Content] = []
        for item in content:
            if not isinstance(item, TextContent):
                continue
            try:
                data = json.loads(item.text)
                summary = self.navigator.get_structure_summary(data, max_depth)
                result_text = "Structure Navigation Summary:\n\n"
                result_text += f"Type: {summary['type']}\n"
                result_text += f"Size: {json.dumps(summary['size'], indent=2)}\n\n"
                result_text += f"Structure:\n{json.dumps(summary['keys'], indent=2)}\n\n"
                result_text += f"Sample Data:\n{json.dumps(summary['sample'], indent=2)}\n\n"
                result_text += f"Statistics:\n{json.dumps(summary['statistics'], indent=2)}\n"
                results.append(TextContent(type="text", text=result_text))
            except json.JSONDecodeError:
                text = item.text
                result_text = "Text Structure Summary:\n\n"
                result_text += f"Length: {len(text)} characters\n"
                result_text += f"Lines: {len(text.split(chr(10)))}\n"
                result_text += f"Words: {len(text.split())}\n"
                result_text += f"First 200 chars: {text[:200]}...\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No content to navigate.")]

    async def _apply_structure_navigation_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async structure navigation that offloads CPU work to thread pool."""
        max_depth = grep_spec.get("maxDepth", 3)
        results: List[Content] = []
        
        for item in content:
            if not isinstance(item, TextContent):
                continue
            
            try:
                # Offload JSON parsing and structure analysis
                if self.executor_manager:
                    data = await self.executor_manager.run_cpu_bound(json.loads, item.text)
                    summary = await self.executor_manager.run_cpu_bound(
                        self.navigator.get_structure_summary,
                        data,
                        max_depth
                    )
                else:
                    data = json.loads(item.text)
                    summary = self.navigator.get_structure_summary(data, max_depth)
                
                # JSON dumps can also be CPU-bound for large structures
                if self.executor_manager:
                    result_text = "Structure Navigation Summary:\n\n"
                    result_text += f"Type: {summary['type']}\n"
                    size_str = await self.executor_manager.run_cpu_bound(
                        lambda s: json.dumps(s, indent=2), summary['size']
                    )
                    result_text += f"Size: {size_str}\n\n"
                    keys_str = await self.executor_manager.run_cpu_bound(
                        lambda s: json.dumps(s, indent=2), summary['keys']
                    )
                    result_text += f"Structure:\n{keys_str}\n\n"
                    sample_str = await self.executor_manager.run_cpu_bound(
                        lambda s: json.dumps(s, indent=2), summary['sample']
                    )
                    result_text += f"Sample Data:\n{sample_str}\n\n"
                    stats_str = await self.executor_manager.run_cpu_bound(
                        lambda s: json.dumps(s, indent=2), summary['statistics']
                    )
                    result_text += f"Statistics:\n{stats_str}\n"
                else:
                    result_text = "Structure Navigation Summary:\n\n"
                    result_text += f"Type: {summary['type']}\n"
                    result_text += f"Size: {json.dumps(summary['size'], indent=2)}\n\n"
                    result_text += f"Structure:\n{json.dumps(summary['keys'], indent=2)}\n\n"
                    result_text += f"Sample Data:\n{json.dumps(summary['sample'], indent=2)}\n\n"
                    result_text += f"Statistics:\n{json.dumps(summary['statistics'], indent=2)}\n"
                
                results.append(TextContent(type="text", text=result_text))
            except json.JSONDecodeError:
                # For non-JSON text, structure analysis is lightweight
                text = item.text
                result_text = "Text Structure Summary:\n\n"
                result_text += f"Length: {len(text)} characters\n"
                result_text += f"Lines: {len(text.split(chr(10)))}\n"
                result_text += f"Words: {len(text.split())}\n"
                result_text += f"First 200 chars: {text[:200]}...\n"
                results.append(TextContent(type="text", text=result_text))

        return results if results else [TextContent(type="text", text="No content to navigate.")]

    def _apply_regex_search(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        pattern = grep_spec.get("pattern", "")
        case_insensitive = grep_spec.get("caseInsensitive", False)
        max_matches = grep_spec.get("maxMatches")
        target = grep_spec.get("target", "content")
        multiline = grep_spec.get("multiline", False)

        context_lines = grep_spec.get("contextLines", {})
        context_before = context_lines.get("before", 0) if isinstance(context_lines, dict) else 0
        context_after = context_lines.get("after", 0) if isinstance(context_lines, dict) else 0
        context_both = context_lines.get("both", 0) if isinstance(context_lines, dict) else 0
        if context_both > 0:
            context_before = context_both
            context_after = context_both

        if not pattern:
            return content

        try:
            flags = re.IGNORECASE if case_insensitive else 0
            if multiline:
                flags |= re.MULTILINE | re.DOTALL
            regex = re.compile(pattern, flags)
        except re.error as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Invalid regex pattern '{pattern}': {e}",
                )
            ]

        filtered: List[Content] = []
        match_count = 0

        for item in content:
            if isinstance(item, TextContent):
                text = item.text

                if target == "structuredContent":
                    try:
                        data = json.loads(text)
                        matches = GrepProcessor._search_in_structure(
                            data, regex, max_matches, match_count
                        )
                        if matches is not None and matches != {} and matches != []:
                            filtered.append(
                                TextContent(type="text", text=json.dumps(matches, indent=2))
                            )
                            if isinstance(matches, list):
                                match_count += len(matches)
                            elif isinstance(matches, dict):
                                match_count += GrepProcessor._count_dict_matches(matches)
                            else:
                                match_count += 1
                    except json.JSONDecodeError:
                        text_matches, match_lines = GrepProcessor._search_in_text(
                            text, regex, max_matches, match_count, context_before, context_after, multiline
                        )
                        if text_matches:
                            filtered.append(TextContent(type="text", text=text_matches))
                            match_count += match_lines
                else:
                    text_matches, match_lines = GrepProcessor._search_in_text(
                        text, regex, max_matches, match_count, context_before, context_after, multiline
                    )
                    if text_matches:
                        filtered.append(TextContent(type="text", text=text_matches))
                        match_count += match_lines

            if max_matches and match_count >= max_matches:
                break

        return filtered if filtered else [TextContent(type="text", text="No matches found.")]

    async def _apply_regex_search_async(
        self, content: List[Content], grep_spec: Dict[str, Any]
    ) -> List[Content]:
        """Async regex search that offloads CPU work to thread pool."""
        pattern = grep_spec.get("pattern", "")
        case_insensitive = grep_spec.get("caseInsensitive", False)
        max_matches = grep_spec.get("maxMatches")
        target = grep_spec.get("target", "content")
        multiline = grep_spec.get("multiline", False)

        context_lines = grep_spec.get("contextLines", {})
        context_before = context_lines.get("before", 0) if isinstance(context_lines, dict) else 0
        context_after = context_lines.get("after", 0) if isinstance(context_lines, dict) else 0
        context_both = context_lines.get("both", 0) if isinstance(context_lines, dict) else 0
        if context_both > 0:
            context_before = context_both
            context_after = context_both

        if not pattern:
            return content

        try:
            flags = re.IGNORECASE if case_insensitive else 0
            if multiline:
                flags |= re.MULTILINE | re.DOTALL
            regex = re.compile(pattern, flags)
        except re.error as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Invalid regex pattern '{pattern}': {e}",
                )
            ]

        filtered: List[Content] = []
        match_count = 0

        for item in content:
            if isinstance(item, TextContent):
                text = item.text

                if target == "structuredContent":
                    try:
                        # Offload JSON parsing
                        if self.executor_manager:
                            data = await self.executor_manager.run_cpu_bound(json.loads, text)
                            # Offload structured search
                            matches = await self.executor_manager.run_cpu_bound(
                                self._search_in_structure,
                                data,
                                regex,
                                max_matches,
                                match_count
                            )
                        else:
                            data = json.loads(text)
                            matches = self._search_in_structure(data, regex, max_matches, match_count)
                        
                        if matches is not None and matches != {} and matches != []:
                            if self.executor_manager:
                                result_text = await self.executor_manager.run_cpu_bound(
                                    lambda m: json.dumps(m, indent=2), matches
                                )
                            else:
                                result_text = json.dumps(matches, indent=2)
                            filtered.append(TextContent(type="text", text=result_text))
                            if isinstance(matches, list):
                                match_count += len(matches)
                            elif isinstance(matches, dict):
                                match_count += self._count_dict_matches(matches)
                            else:
                                match_count += 1
                    except json.JSONDecodeError:
                        # Fallback to text search
                        if self.executor_manager:
                            text_matches, match_lines = await self.executor_manager.run_cpu_bound(
                                self._search_in_text,
                                text,
                                regex,
                                max_matches,
                                match_count,
                                context_before,
                                context_after,
                                multiline
                            )
                        else:
                            text_matches, match_lines = self._search_in_text(
                                text, regex, max_matches, match_count, context_before, context_after, multiline
                            )
                        if text_matches:
                            filtered.append(TextContent(type="text", text=text_matches))
                            match_count += match_lines
                else:
                    # Offload text search for large texts
                    if self.executor_manager and len(text) > 10000:
                        text_matches, match_lines = await self.executor_manager.run_cpu_bound(
                            self._search_in_text,
                            text,
                            regex,
                            max_matches,
                            match_count,
                            context_before,
                            context_after,
                            multiline
                        )
                    else:
                        text_matches, match_lines = self._search_in_text(
                            text, regex, max_matches, match_count, context_before, context_after, multiline
                        )
                    if text_matches:
                        filtered.append(TextContent(type="text", text=text_matches))
                        match_count += match_lines

            if max_matches and match_count >= max_matches:
                break

        return filtered if filtered else [TextContent(type="text", text="No matches found.")]

    # -- Static helpers kept for regex search --------------------------------

    @staticmethod
    def _search_in_text(
        text: str,
        regex: re.Pattern,
        max_matches: Optional[int],
        current_count: int,
        context_before: int = 0,
        context_after: int = 0,
        multiline: bool = False,
    ) -> Tuple[str, int]:
        if multiline:
            matches = list(regex.finditer(text))
            if not matches:
                return "", 0
            if max_matches:
                remaining = max_matches - current_count
                if remaining <= 0:
                    return "", 0
                matches = matches[:remaining]
            result_parts = [m.group(0) for m in matches]
            return "\n---\n".join(result_parts), len(matches)

        lines = text.split("\n")
        matched_line_indices: set[int] = set()

        for i, line in enumerate(lines):
            if regex.search(line):
                matched_line_indices.add(i)

        if not matched_line_indices:
            return "", 0

        if max_matches:
            remaining = max_matches - current_count
            if remaining <= 0:
                return "", 0
            matched_line_indices = set(sorted(matched_line_indices)[:remaining])

        included_indices: set[int] = set()
        result_lines: List[str] = []
        actual_match_count = 0

        for match_idx in sorted(matched_line_indices):
            for i in range(max(0, match_idx - context_before), match_idx):
                if i not in included_indices:
                    result_lines.append(lines[i])
                    included_indices.add(i)

            if match_idx not in included_indices:
                result_lines.append(lines[match_idx])
                included_indices.add(match_idx)
                actual_match_count += 1

            for i in range(match_idx + 1, min(len(lines), match_idx + 1 + context_after)):
                if i not in included_indices:
                    result_lines.append(lines[i])
                    included_indices.add(i)

            if context_before > 0 or context_after > 0:
                next_match = min(
                    (m for m in matched_line_indices if m > match_idx), default=None
                )
                if next_match and next_match > match_idx + context_after + 1:
                    result_lines.append("---")

        return "\n".join(result_lines), actual_match_count

    @staticmethod
    def _search_in_structure(
        data: Any,
        regex: re.Pattern,
        max_matches: Optional[int],
        current_count: int,
    ) -> Any:
        if max_matches and current_count >= max_matches:
            return None

        if isinstance(data, dict):
            matches: Dict[str, Any] = {}
            count = current_count
            for key, value in data.items():
                if max_matches and count >= max_matches:
                    break
                key_matches = regex.search(str(key))
                value_matches = isinstance(value, str) and regex.search(value)

                if key_matches or value_matches:
                    matches[key] = value
                    count += 1
                elif isinstance(value, (dict, list)):
                    nested = GrepProcessor._search_in_structure(value, regex, max_matches, count)
                    if nested is not None and nested != {} and nested != []:
                        matches[key] = nested
                        count += 1
            return matches if matches else None

        elif isinstance(data, list):
            list_matches: List[Any] = []
            count = current_count
            for item in data:
                if max_matches and count >= max_matches:
                    break
                if isinstance(item, (dict, list)):
                    nested = GrepProcessor._search_in_structure(item, regex, max_matches, count)
                    if nested is not None and nested != {} and nested != []:
                        list_matches.append(nested)
                        count += 1
                elif isinstance(item, str) and regex.search(item):
                    list_matches.append(item)
                    count += 1
            return list_matches if list_matches else None
        else:
            if regex.search(str(data)):
                return data
            return None

    @staticmethod
    def _count_dict_matches(matches: Dict[str, Any]) -> int:
        count = 0
        for value in matches.values():
            if isinstance(value, dict):
                count += GrepProcessor._count_dict_matches(value)
            elif isinstance(value, list):
                count += len(value)
            else:
                count += 1
        return count


# ---------------------------------------------------------------------------
# Processor pipeline
# ---------------------------------------------------------------------------

class ProcessorPipeline:
    """Composes multiple ``BaseProcessor`` instances into a sequential pipeline.

    Each processor is invoked only if a matching key exists in *specs*.
    """

    def __init__(self, processors: Optional[List[BaseProcessor]] = None) -> None:
        self.processors: List[BaseProcessor] = processors or []

    def add(self, processor: BaseProcessor) -> "ProcessorPipeline":
        self.processors.append(processor)
        return self

    def execute(
        self, content: List[Content], specs: Dict[str, Dict[str, Any]]
    ) -> ProcessorResult:
        """Run the pipeline synchronously, returning a merged ``ProcessorResult``."""
        current_content = content
        original_size = _measure_content(content)
        total_metadata: Dict[str, Any] = {}

        for processor in self.processors:
            key = processor.name
            if key not in specs:
                continue
            proc_result = processor.process(current_content, specs[key])
            current_content = proc_result.content
            total_metadata[key] = proc_result.metadata

        filtered_size = _measure_content(current_content)
        return ProcessorResult(
            content=current_content,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata=total_metadata,
        )

    async def execute_async(
        self, content: List[Content], specs: Dict[str, Dict[str, Any]]
    ) -> ProcessorResult:
        """Run the pipeline asynchronously, returning a merged ``ProcessorResult``."""
        current_content = content
        original_size = _measure_content(content)
        total_metadata: Dict[str, Any] = {}

        for processor in self.processors:
            key = processor.name
            if key not in specs:
                continue
            
            # Use async version if available, otherwise fall back to sync
            if hasattr(processor, 'process_async'):
                proc_result = await processor.process_async(current_content, specs[key])
            else:
                proc_result = processor.process(current_content, specs[key])
            
            current_content = proc_result.content
            total_metadata[key] = proc_result.metadata

        filtered_size = _measure_content(current_content)
        return ProcessorResult(
            content=current_content,
            original_size=original_size,
            filtered_size=filtered_size,
            metadata=total_metadata,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _measure_content(content: List[Content]) -> int:
    """Return total character count across all TextContent items."""
    return sum(len(item.text) for item in content if isinstance(item, TextContent))
