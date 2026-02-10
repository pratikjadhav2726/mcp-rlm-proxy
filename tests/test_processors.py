"""
Unit tests for ProjectionProcessor, GrepProcessor, ProcessorResult,
ProcessorPipeline, and BaseProcessor.
"""

import json
import pytest
from mcp.types import TextContent

from mcp_proxy.processors import (
    GrepProcessor,
    ProcessorPipeline,
    ProcessorResult,
    ProjectionProcessor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projection_processor():
    return ProjectionProcessor()


@pytest.fixture
def grep_processor():
    return GrepProcessor()


# ---------------------------------------------------------------------------
# ProjectionProcessor
# ---------------------------------------------------------------------------

class TestProjectionProcessor:
    """Tests for ProjectionProcessor."""

    def test_include_mode_simple(self):
        data = {
            "name": "John",
            "email": "john@example.com",
            "age": 30,
            "city": "New York",
        }
        projection = {"mode": "include", "fields": ["name", "email"]}
        result = ProjectionProcessor.apply_projection(data, projection)
        assert result == {"name": "John", "email": "john@example.com"}

    def test_exclude_mode_simple(self):
        data = {
            "name": "John",
            "email": "john@example.com",
            "password": "secret123",
            "ssn": "123-45-6789",
        }
        projection = {"mode": "exclude", "fields": ["password", "ssn"]}
        result = ProjectionProcessor.apply_projection(data, projection)
        assert "password" not in result
        assert "ssn" not in result
        assert "name" in result
        assert "email" in result

    def test_include_mode_nested(self):
        data = {
            "user": {
                "name": "John",
                "email": "john@example.com",
                "address": {"street": "123 Main St", "city": "New York"},
            },
            "metadata": {"created": "2024-01-01"},
        }
        projection = {"mode": "include", "fields": ["user.name", "user.email"]}
        result = ProjectionProcessor.apply_projection(data, projection)
        assert "user" in result
        assert result["user"] == {"name": "John", "email": "john@example.com"}

    def test_include_mode_with_arrays(self):
        data = {
            "users": [
                {"name": "John", "email": "john@example.com", "age": 30},
                {"name": "Jane", "email": "jane@example.com", "age": 25},
            ]
        }
        projection = {"mode": "include", "fields": ["users.name", "users.email"]}
        result = ProjectionProcessor.apply_projection(data, projection)
        assert "users" in result
        assert len(result["users"]) == 2
        assert result["users"][0] == {"name": "John", "email": "john@example.com"}
        assert result["users"][1] == {"name": "Jane", "email": "jane@example.com"}

    def test_exclude_mode_nested(self):
        data = {
            "user": {
                "name": "John",
                "email": "john@example.com",
                "password": "secret123",
            }
        }
        projection = {"mode": "exclude", "fields": ["user.password"]}
        result = ProjectionProcessor.apply_projection(data, projection)
        assert "user" in result
        assert "password" not in result["user"]
        assert "name" in result["user"]
        assert "email" in result["user"]

    def test_project_content_json(self):
        json_data = {"name": "John", "email": "john@example.com", "age": 30, "city": "New York"}
        content = [TextContent(type="text", text=json.dumps(json_data))]
        projection = {"mode": "include", "fields": ["name", "email"]}
        result = ProjectionProcessor.project_content(content, projection)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        parsed = json.loads(result[0].text)
        assert parsed == {"name": "John", "email": "john@example.com"}

    def test_project_content_plain_text(self):
        content = [TextContent(type="text", text="This is plain text")]
        projection = {"mode": "include", "fields": ["name"]}
        result = ProjectionProcessor.project_content(content, projection)
        assert len(result) == 1
        assert result[0].text == "This is plain text"

    def test_process_returns_processor_result(self, projection_processor):
        """BaseProcessor.process() returns a ProcessorResult."""
        json_data = {"name": "John", "email": "john@example.com", "age": 30}
        content = [TextContent(type="text", text=json.dumps(json_data))]
        spec = {"mode": "include", "fields": ["name"]}
        result = projection_processor.process(content, spec)
        assert isinstance(result, ProcessorResult)
        assert result.filtered_size < result.original_size
        assert result.metadata["applied"] is True
        assert result.metadata["mode"] == "include"

    def test_process_validates_mode(self, projection_processor):
        content = [TextContent(type="text", text='{"a": 1}')]
        with pytest.raises(ValueError, match="Invalid projection mode"):
            projection_processor.process(content, {"mode": "bad", "fields": ["a"]})

    def test_process_validates_fields(self, projection_processor):
        content = [TextContent(type="text", text='{"a": 1}')]
        with pytest.raises(ValueError, match="non-empty"):
            projection_processor.process(content, {"mode": "include", "fields": []})


# ---------------------------------------------------------------------------
# GrepProcessor
# ---------------------------------------------------------------------------

class TestGrepProcessor:
    """Tests for GrepProcessor (now instance-based)."""

    def test_grep_simple_text(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1: INFO message\nLine 2: ERROR occurred\nLine 3: WARN message",
            )
        ]
        grep_spec = {"pattern": "ERROR", "caseInsensitive": False}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        assert "ERROR" in result[0].text
        assert "INFO" not in result[0].text

    def test_grep_case_insensitive(self, grep_processor):
        content = [
            TextContent(type="text", text="Line 1: error\nLine 2: ERROR\nLine 3: Error")
        ]
        grep_spec = {"pattern": "error", "caseInsensitive": True}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        lines = result[0].text.split("\n")
        assert len(lines) == 3

    def test_grep_max_matches(self, grep_processor):
        content = [
            TextContent(type="text", text="\n".join([f"ERROR {i}" for i in range(10)]))
        ]
        grep_spec = {"pattern": "ERROR", "maxMatches": 5}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        lines = result[0].text.split("\n")
        assert len([line for line in lines if line]) <= 5

    def test_grep_structured_content(self, grep_processor):
        json_data = {
            "users": [
                {"name": "John", "email": "john@gmail.com"},
                {"name": "Jane", "email": "jane@yahoo.com"},
                {"name": "Bob", "email": "bob@gmail.com"},
            ]
        }
        content = [TextContent(type="text", text=json.dumps(json_data))]
        grep_spec = {"pattern": "gmail", "target": "structuredContent", "caseInsensitive": True}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert "users" in parsed
        assert len(parsed["users"]) == 2

    def test_grep_invalid_pattern(self, grep_processor):
        content = [TextContent(type="text", text="Some text")]
        grep_spec = {"pattern": "[invalid regex", "caseInsensitive": False}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        assert "error" in result[0].text.lower()

    def test_grep_no_matches(self, grep_processor):
        content = [TextContent(type="text", text="Line 1: INFO\nLine 2: DEBUG")]
        grep_spec = {"pattern": "ERROR", "caseInsensitive": False}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        assert "No matches" in result[0].text

    def test_grep_regex_pattern(self, grep_processor):
        content = [
            TextContent(type="text", text="ERROR: Failed\nWARN: Warning\nINFO: Success")
        ]
        grep_spec = {"pattern": "ERROR|WARN", "caseInsensitive": False}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        assert "ERROR" in result[0].text
        assert "WARN" in result[0].text
        assert "INFO" not in result[0].text

    def test_grep_context_lines_before(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1: INFO\nLine 2: DEBUG\nLine 3: ERROR\nLine 4: WARN\nLine 5: INFO",
            )
        ]
        grep_spec = {"pattern": "ERROR", "contextLines": {"before": 2}}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Line 1: INFO" in text
        assert "Line 2: DEBUG" in text
        assert "Line 3: ERROR" in text
        assert "Line 4: WARN" not in text

    def test_grep_context_lines_after(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1: INFO\nLine 2: ERROR\nLine 3: DEBUG\nLine 4: WARN\nLine 5: INFO",
            )
        ]
        grep_spec = {"pattern": "ERROR", "contextLines": {"after": 2}}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Line 2: ERROR" in text
        assert "Line 3: DEBUG" in text
        assert "Line 4: WARN" in text
        assert "Line 1: INFO" not in text

    def test_grep_context_lines_both(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1: INFO\nLine 2: DEBUG\nLine 3: ERROR\nLine 4: WARN\nLine 5: INFO",
            )
        ]
        grep_spec = {"pattern": "ERROR", "contextLines": {"both": 1}}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Line 2: DEBUG" in text
        assert "Line 3: ERROR" in text
        assert "Line 4: WARN" in text
        assert "Line 1: INFO" not in text
        assert "Line 5: INFO" not in text

    def test_grep_context_lines_multiple_matches(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1: INFO\nLine 2: ERROR\nLine 3: DEBUG\nLine 4: ERROR\nLine 5: WARN",
            )
        ]
        grep_spec = {"pattern": "ERROR", "contextLines": {"both": 1}}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Line 2: ERROR" in text
        assert "Line 3: DEBUG" in text
        assert "Line 4: ERROR" in text
        assert "Line 5: WARN" in text

    def test_grep_multiline_pattern(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="def my_function():\n    return True\n\ndef other():\n    pass",
            )
        ]
        grep_spec = {
            "pattern": "def my_function\\(\\).*?return True",
            "multiline": True,
        }
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "def my_function()" in text
        assert "return True" in text
        assert "def other()" not in text

    def test_grep_multiline_with_dotall(self, grep_processor):
        content = [TextContent(type="text", text="Start\nMiddle\nEnd\nOther")]
        grep_spec = {"pattern": "Start.*End", "multiline": True}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Start" in text
        assert "End" in text
        assert "Middle" in text

    def test_grep_multiline_without_flag(self, grep_processor):
        content = [TextContent(type="text", text="Start\nMiddle\nEnd")]
        grep_spec = {"pattern": "Start.*End", "multiline": False}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        assert "No matches" in result[0].text

    def test_grep_context_and_multiline(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="Line 1\nLine 2\nStart\nMiddle\nEnd\nLine 6\nLine 7",
            )
        ]
        grep_spec = {"pattern": "Start.*End", "multiline": True}
        result = grep_processor.apply_grep(content, grep_spec)
        assert len(result) == 1
        text = result[0].text
        assert "Start" in text
        assert "End" in text
        assert "Middle" in text

    def test_process_returns_processor_result(self, grep_processor):
        """BaseProcessor.process() returns a ProcessorResult."""
        content = [
            TextContent(type="text", text="Line 1: INFO\nLine 2: ERROR\nLine 3: WARN")
        ]
        spec = {"pattern": "ERROR"}
        result = grep_processor.process(content, spec)
        assert isinstance(result, ProcessorResult)
        assert result.metadata["applied"] is True
        assert result.metadata["mode"] == "regex"

    def test_bm25_mode(self, grep_processor):
        content = [
            TextContent(
                type="text",
                text="The database connection failed. Another paragraph about cats. "
                "Database timeout error occurred in production.",
            )
        ]
        spec = {"mode": "bm25", "query": "database error", "topK": 2}
        result = grep_processor.apply_grep(content, spec)
        assert len(result) >= 1
        assert "BM25" in result[0].text or "No relevant" in result[0].text

    def test_fuzzy_mode(self, grep_processor):
        content = [TextContent(type="text", text="The MacBook Pro is a powerful laptop.")]
        spec = {"mode": "fuzzy", "pattern": "MacBok", "threshold": 0.7}
        result = grep_processor.apply_grep(content, spec)
        assert len(result) >= 1

    def test_structure_mode(self, grep_processor):
        data = {"users": [{"name": "John"}, {"name": "Jane"}], "count": 2}
        content = [TextContent(type="text", text=json.dumps(data))]
        spec = {"mode": "structure", "maxDepth": 2}
        result = grep_processor.apply_grep(content, spec)
        assert len(result) == 1
        assert "Structure" in result[0].text

    def test_unknown_mode_returns_error(self, grep_processor):
        content = [TextContent(type="text", text="hello")]
        result = grep_processor.apply_grep(content, {"mode": "unknown", "pattern": "x"})
        assert "Error" in result[0].text


# ---------------------------------------------------------------------------
# ProcessorPipeline
# ---------------------------------------------------------------------------

class TestProcessorPipeline:
    """Tests for ProcessorPipeline."""

    def test_pipeline_projection_only(self):
        pipeline = ProcessorPipeline([ProjectionProcessor()])
        data = {"name": "John", "age": 30, "city": "NYC"}
        content = [TextContent(type="text", text=json.dumps(data))]
        result = pipeline.execute(content, {"projection": {"mode": "include", "fields": ["name"]}})
        assert isinstance(result, ProcessorResult)
        parsed = json.loads(result.content[0].text)
        assert parsed == {"name": "John"}
        assert "projection" in result.metadata

    def test_pipeline_grep_only(self):
        pipeline = ProcessorPipeline([GrepProcessor()])
        content = [TextContent(type="text", text="INFO ok\nERROR bad\nDEBUG meh")]
        result = pipeline.execute(content, {"grep": {"pattern": "ERROR"}})
        assert "ERROR" in result.content[0].text
        assert "grep" in result.metadata

    def test_pipeline_both(self):
        pipeline = ProcessorPipeline([ProjectionProcessor(), GrepProcessor()])
        data = {"log": "INFO ok\nERROR bad\nDEBUG meh", "extra": "ignored"}
        content = [TextContent(type="text", text=json.dumps(data))]
        # First project, then grep
        result = pipeline.execute(
            content,
            {
                "projection": {"mode": "include", "fields": ["log"]},
                "grep": {"pattern": "ERROR"},
            },
        )
        assert isinstance(result, ProcessorResult)
        assert "projection" in result.metadata
        assert "grep" in result.metadata

    def test_pipeline_skips_unused_processors(self):
        pipeline = ProcessorPipeline([ProjectionProcessor(), GrepProcessor()])
        content = [TextContent(type="text", text="hello world")]
        result = pipeline.execute(content, {})  # no specs
        assert result.content[0].text == "hello world"
        assert result.metadata == {}

    def test_savings_percent(self):
        result = ProcessorResult(
            content=[], original_size=1000, filtered_size=100
        )
        assert result.savings_percent == 90.0

    def test_savings_percent_zero_original(self):
        result = ProcessorResult(content=[], original_size=0, filtered_size=0)
        assert result.savings_percent == 0.0


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
