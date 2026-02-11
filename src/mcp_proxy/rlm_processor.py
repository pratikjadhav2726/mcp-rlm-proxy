"""
RLM-inspired processors for recursive context management.

Based on principles from "Recursive Language Models" (arXiv:2512.24601):
- Treat tool outputs as external environments
- Enable programmatic exploration through recursive calls
- Support snippet-based processing to minimize context usage
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from mcp.types import Content, TextContent

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


class RecursiveContextManager:
    """
    Manages recursive context decomposition for large tool outputs.
    
    Inspired by RLM paper's approach to handling arbitrarily long prompts
    by treating them as external environments that can be explored programmatically.
    """
    
    def __init__(self):
        self.max_chunk_size = 10000  # Max tokens per chunk
        self.exploration_depth = 0
        self.max_depth = 10
    
    def should_decompose(self, content: List[Content]) -> bool:
        """
        Determine if content should be decomposed recursively.
        
        Args:
            content: List of Content objects
            
        Returns:
            True if content is large enough to benefit from decomposition
        """
        total_size = sum(
            len(item.text) for item in content 
            if isinstance(item, TextContent)
        )
        return total_size > self.max_chunk_size
    
    def suggest_exploration_strategy(self, content: List[Content]) -> Dict[str, Any]:
        """
        Analyze content and suggest an exploration strategy for agents.
        
        This implements the RLM principle of "programmatic exploration" by
        analyzing the structure of the output and suggesting how to recursively
        explore it.
        
        Args:
            content: List of Content objects
            
        Returns:
            Dictionary with exploration suggestions
        """
        suggestions = {
            "should_decompose": False,
            "strategies": [],
            "estimated_savings": 0,
        }
        
        for item in content:
            if not isinstance(item, TextContent):
                continue
                
            text = item.text
            
            # Try to parse as JSON for structured exploration
            try:
                data = json.loads(text)
                
                if isinstance(data, dict):
                    # Suggest field-based exploration via proxy_filter
                    keys = list(data.keys())
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "proxy_filter",
                        "description": "Use proxy_filter to project specific fields from the cached result",
                        "available_fields": keys[:10],  # Show first 10 fields
                        "total_fields": len(keys),
                        "example": {
                            "tool": "proxy_filter",
                            "arguments": {
                                "cache_id": "<CACHE_ID_FROM_TRUNCATED_RESPONSE>",
                                "fields": keys[:3],
                                    "mode": "include",
                            },
                        }
                    })
                    
                    # Check for arrays that can be explored recursively
                    array_fields = [k for k, v in data.items() if isinstance(v, list)]
                    if array_fields:
                        suggestions["strategies"].append({
                            "type": "proxy_filter_array",
                            "description": "Use proxy_filter to explore array fields element by element",
                            "array_fields": array_fields,
                            "example": {
                                "tool": "proxy_filter",
                                "arguments": {
                                    "cache_id": "<CACHE_ID_FROM_TRUNCATED_RESPONSE>",
                                    "fields": [f"{array_fields[0]}.id", f"{array_fields[0]}.name"],
                                        "mode": "include",
                                },
                            }
                        })
                    
                    # Estimate savings
                    full_size = len(text)
                    projected_size = full_size // max(len(keys), 1) * 3  # Assume accessing 3 fields
                    suggestions["estimated_savings"] = max(0, full_size - projected_size)
                
                elif isinstance(data, list):
                    # Suggest pagination or filtering via proxy_filter / proxy_explore
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "list_pagination",
                        "description": "Use proxy_filter or proxy_explore to process list in chunks",
                        "list_length": len(data),
                        "example": {
                            "tool": "proxy_filter",
                            "arguments": {
                                "cache_id": "<CACHE_ID_FROM_TRUNCATED_RESPONSE>",
                                "fields": ["[0:10]"],  # First 10 items (pseudo-syntax)
                                    "mode": "include",
                            },
                        },
                    })
                    
            except json.JSONDecodeError:
                # Plain text - suggest proxy_search-based exploration
                lines = text.split("\n")
                if len(lines) > 100:
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "proxy_search",
                        "description": "Use proxy_search to search within large cached text",
                        "total_lines": len(lines),
                        "example": {
                            "tool": "proxy_search",
                            "arguments": {
                                "cache_id": "<CACHE_ID_FROM_TRUNCATED_RESPONSE>",
                                    "pattern": "ERROR|WARN",
                                "mode": "regex",
                                "max_results": 20,
                                "context_lines": 2,
                            },
                        }
                    })
                    
                    # Estimate savings
                    full_size = len(text)
                    grep_size = 20 * 100  # 20 matches * ~100 chars each
                    suggestions["estimated_savings"] = max(0, full_size - grep_size)
        
        return suggestions
    
    def create_exploration_metadata(
        self,
        content: List[Content],
        cache_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create metadata that can be returned with responses to guide recursive exploration.
        
        Args:
            content: List of Content objects
            
        Returns:
            Metadata dictionary or None if not applicable
        """
        suggestions = self.suggest_exploration_strategy(content)
        
        if not suggestions["should_decompose"]:
            return None

        # Build concrete next_steps in the spirit of RLM: explicit follow-up calls
        next_steps: List[Dict[str, Any]] = []
        for strategy in suggestions["strategies"]:
            example = strategy.get("example") or {}
            tool = example.get("tool")
            arguments = dict(example.get("arguments") or {})

            # Thread through real cache_id if available
            if cache_id and "cache_id" in arguments:
                arguments["cache_id"] = cache_id

            if tool:
                next_steps.append(
                    {
                        "tool": tool,
                        "when": strategy.get("description") or "",
                        "arguments": arguments,
                    }
                )
        
        return {
            "rlm_hints": {
                "recursive_exploration_available": True,
                "strategies": suggestions["strategies"],
                "next_steps": next_steps,
                "estimated_token_savings": suggestions["estimated_savings"],
                "hint": (
                    "This response is large. Consider using exactly one of the proxy tools "
                    "`proxy_filter`, `proxy_search`, or `proxy_explore` with the provided "
                    "cache_id, based on the suggested next_steps."
                ),
            }
        }


class ChunkProcessor:
    """
    Process large outputs in chunks for efficient context management.
    
    Implements snippet processing from RLM paper.
    """
    
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 10000, overlap: int = 200) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks for context-aware processing.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum size of each chunk
            overlap: Number of characters to overlap between chunks
            
        Returns:
            List of chunk dictionaries with metadata
        """
        if len(text) <= chunk_size:
            return [{
                "text": text,
                "index": 0,
                "total_chunks": 1,
                "start": 0,
                "end": len(text)
            }]
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # Try to break at a newline if possible
            if end < len(text):
                newline_pos = text.rfind("\n", start, end)
                if newline_pos != -1 and newline_pos > start + chunk_size // 2:
                    end = newline_pos + 1
            
            chunks.append({
                "text": text[start:end],
                "index": chunk_index,
                "total_chunks": -1,  # Will be updated
                "start": start,
                "end": end
            })
            
            start = end - overlap if end < len(text) else end
            chunk_index += 1
        
        # Update total_chunks
        total = len(chunks)
        for chunk in chunks:
            chunk["total_chunks"] = total
        
        return chunks
    
    @staticmethod
    def merge_chunks(chunks: List[Dict[str, Any]], deduplicate: bool = True) -> str:
        """
        Merge processed chunks back into a single text.
        
        Args:
            chunks: List of chunk dictionaries
            deduplicate: Remove overlapping content
            
        Returns:
            Merged text
        """
        if not chunks:
            return ""
        
        if len(chunks) == 1:
            return chunks[0]["text"]
        
        # Sort by index
        sorted_chunks = sorted(chunks, key=lambda x: x["index"])
        
        if not deduplicate:
            return "".join(c["text"] for c in sorted_chunks)
        
        # Deduplicate overlaps (simplified approach)
        result = [sorted_chunks[0]["text"]]
        
        for i in range(1, len(sorted_chunks)):
            prev_end = sorted_chunks[i-1]["end"]
            curr_start = sorted_chunks[i]["start"]
            
            if curr_start < prev_end:
                # There's overlap - skip the overlapping part
                overlap_size = prev_end - curr_start
                result.append(sorted_chunks[i]["text"][overlap_size:])
            else:
                result.append(sorted_chunks[i]["text"])

class FieldDiscoveryHelper:
    """
    Helper to discover available fields in structured data for recursive exploration.
    """
    
    @staticmethod
    def discover_fields(data: Any, max_depth: int = 3, current_depth: int = 0, prefix: str = "") -> List[str]:
        """
        Recursively discover all field paths in structured data.
        
        Args:
            data: Data to analyze (dict, list, or primitive)
            max_depth: Maximum recursion depth
            current_depth: Current depth (internal)
            prefix: Path prefix (internal)
            
        Returns:
            List of field paths (e.g., ["name", "user.email", "items[].id"])
        """
        if current_depth >= max_depth:
            return []
        
        fields = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                field_path = f"{prefix}.{key}" if prefix else key
                fields.append(field_path)
                
                # Recursively discover nested fields
                if isinstance(value, (dict, list)):
                    nested = FieldDiscoveryHelper.discover_fields(
                        value, max_depth, current_depth + 1, field_path
                    )
                    fields.extend(nested)
        
        elif isinstance(data, list) and len(data) > 0:
            # Analyze first item of array
            array_path = f"{prefix}[]" if prefix else "[]"
            if isinstance(data[0], dict):
                nested = FieldDiscoveryHelper.discover_fields(
                    data[0], max_depth, current_depth + 1, array_path
                )
                fields.extend(nested)
            else:
                fields.append(array_path)
        
        return fields
    
    @staticmethod
    def create_field_summary(data: Any) -> Dict[str, Any]:
        """
        Create a summary of available fields without returning the data itself.
        
        This enables the RLM "discover structure first, then query" pattern.
        
        Args:
            data: Data to analyze
            
        Returns:
            Summary dictionary
        """
        fields = FieldDiscoveryHelper.discover_fields(data, max_depth=3)
        
        summary = {
            "total_fields": len(fields),
            "top_level_fields": [],
            "nested_fields": [],
            "array_fields": [],
            "sample_projection": {}
        }
        
        for field in fields:
            if "." not in field and "[]" not in field:
                summary["top_level_fields"].append(field)
            elif "[]" in field:
                summary["array_fields"].append(field)
            else:
                summary["nested_fields"].append(field)
        
        # Create a sample projection
        sample_fields = summary["top_level_fields"][:5]
        if sample_fields:
            summary["sample_projection"] = {
                "_meta": {
                    "projection": {
                        "mode": "include",
                        "fields": sample_fields
                    }
                }
            }
        
        return summary

