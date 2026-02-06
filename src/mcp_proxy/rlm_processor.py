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
            "estimated_savings": 0
        }
        
        for item in content:
            if not isinstance(item, TextContent):
                continue
                
            text = item.text
            
            # Try to parse as JSON for structured exploration
            try:
                data = json.loads(text)
                
                if isinstance(data, dict):
                    # Suggest field-based exploration
                    keys = list(data.keys())
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "field_projection",
                        "description": "Use projection to access specific fields",
                        "available_fields": keys[:10],  # Show first 10 fields
                        "total_fields": len(keys),
                        "example": {
                            "_meta": {
                                "projection": {
                                    "mode": "include",
                                    "fields": keys[:3]
                                }
                            }
                        }
                    })
                    
                    # Check for arrays that can be explored recursively
                    array_fields = [k for k, v in data.items() if isinstance(v, list)]
                    if array_fields:
                        suggestions["strategies"].append({
                            "type": "array_exploration",
                            "description": "Explore array fields element by element",
                            "array_fields": array_fields,
                            "example": {
                                "_meta": {
                                    "projection": {
                                        "mode": "include",
                                        "fields": [f"{array_fields[0]}.id", f"{array_fields[0]}.name"]
                                    }
                                }
                            }
                        })
                    
                    # Estimate savings
                    full_size = len(text)
                    projected_size = full_size // max(len(keys), 1) * 3  # Assume accessing 3 fields
                    suggestions["estimated_savings"] = max(0, full_size - projected_size)
                
                elif isinstance(data, list):
                    # Suggest pagination or filtering
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "list_pagination",
                        "description": "Process list in chunks using projection",
                        "list_length": len(data),
                        "example": {
                            "_meta": {
                                "projection": {
                                    "mode": "include",
                                    "fields": ["[0:10]"]  # First 10 items (pseudo-syntax)
                                }
                            }
                        }
                    })
                    
            except json.JSONDecodeError:
                # Plain text - suggest grep-based exploration
                lines = text.split("\n")
                if len(lines) > 100:
                    suggestions["should_decompose"] = True
                    suggestions["strategies"].append({
                        "type": "grep_search",
                        "description": "Use grep to search within large text",
                        "total_lines": len(lines),
                        "example": {
                            "_meta": {
                                "grep": {
                                    "pattern": "ERROR|WARN",
                                    "maxMatches": 20,
                                    "contextLines": {"both": 2}
                                }
                            }
                        }
                    })
                    
                    # Estimate savings
                    full_size = len(text)
                    grep_size = 20 * 100  # 20 matches * ~100 chars each
                    suggestions["estimated_savings"] = max(0, full_size - grep_size)
        
        return suggestions
    
    def create_exploration_metadata(self, content: List[Content]) -> Optional[Dict[str, Any]]:
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
        
        return {
            "rlm_hints": {
                "recursive_exploration_available": True,
                "strategies": suggestions["strategies"],
                "estimated_token_savings": suggestions["estimated_savings"],
                "hint": "This response is large. Consider using _meta.projection or _meta.grep to explore it recursively."
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
        
        return "".join(result)


class SmartCacheManager:
    """
    Manages caching of tool outputs for efficient recursive exploration.
    
    Allows agents to make multiple filtered calls to the same large output
    without re-executing the tool.
    """
    
    def __init__(self, max_cache_size: int = 10):
        self.cache: Dict[str, Any] = {}
        self.max_size = max_cache_size
        self.access_count: Dict[str, int] = {}
    
    def cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Generate a cache key for a tool call."""
        # Remove _meta from arguments for cache key
        args_without_meta = {k: v for k, v in arguments.items() if k != "_meta"}
        return f"{tool_name}:{json.dumps(args_without_meta, sort_keys=True)}"
    
    def get(self, key: str) -> Optional[List[Content]]:
        """Get cached content."""
        if key in self.cache:
            self.access_count[key] = self.access_count.get(key, 0) + 1
            logger.debug(f"Cache hit for key: {key[:50]}... (accessed {self.access_count[key]} times)")
            return self.cache[key]
        return None
    
    def put(self, key: str, content: List[Content]):
        """Store content in cache."""
        if len(self.cache) >= self.max_size:
            # Evict least accessed item
            min_key = min(self.access_count.items(), key=lambda x: x[1])[0]
            del self.cache[min_key]
            del self.access_count[min_key]
            logger.debug(f"Evicted cache key: {min_key[:50]}...")
        
        self.cache[key] = content
        self.access_count[key] = 0
        logger.debug(f"Cached result for key: {key[:50]}...")
    
    def clear(self):
        """Clear the cache."""
        self.cache.clear()
        self.access_count.clear()
        logger.debug("Cache cleared")


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

