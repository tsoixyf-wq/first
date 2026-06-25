"""Tests for LLMClient — uses mock OpenAI endpoint."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.llm_client import LLMClient


class TestLLMClient:

    @pytest.mark.asyncio
    async def test_chat_returns_content(self):
        client = LLMClient()
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Hello, world"))
        ]
        with patch.object(client._client.chat.completions, "create", return_value=mock_response):
            result = await client.chat("系统提示", "用户输入")
            assert result == "Hello, world"

    @pytest.mark.asyncio
    async def test_chat_with_json_output_parses_json(self):
        client = LLMClient()
        json_str = '{"score": 8.5, "reasoning": "good match"}'
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(message=AsyncMock(content=json_str))]
        with patch.object(client._client.chat.completions, "create", return_value=mock_response):
            result = await client.chat_with_json_output(
                "系统提示", "用户输入",
                output_schema={"type": "object", "properties": {"score": {"type": "number"}}},
            )
            assert isinstance(result, dict)
            assert result["score"] == 8.5
            assert result["reasoning"] == "good match"

    @pytest.mark.asyncio
    async def test_chat_with_json_markdown_block(self):
        """LLM returns JSON wrapped in ```json block."""
        client = LLMClient()
        json_str = '```json\n{"score": 7.0}\n```'
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(message=AsyncMock(content=json_str))]
        with patch.object(client._client.chat.completions, "create", return_value=mock_response):
            result = await client.chat_with_json_output(
                "system", "user",
                output_schema={"type": "object", "properties": {"score": {"type": "number"}}},
            )
            assert result["score"] == 7.0

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens(self):
        client = LLMClient()
        tokens = ["Hello", ", ", "world", "!"]

        class MockChoice:
            def __init__(self, content):
                self.delta = AsyncMock(content=content)

        mock_chunks = [
            AsyncMock(choices=[MockChoice(t)]) for t in tokens
        ]
        mock_chunks.append(AsyncMock(choices=[MockChoice("")]))  # end

        with patch.object(client._client.chat.completions, "create", return_value=mock_chunks):
            collected = []
            async for token in client.chat_stream("system", "user"):
                collected.append(token)
            assert "".join(collected) == "Hello, world!"

    @pytest.mark.asyncio
    async def test_json_parse_failure_fallback(self):
        """Malformed JSON returns empty dict via fallback."""
        client = LLMClient()
        bad_json = "not valid json at all"
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(message=AsyncMock(content=bad_json))]
        with patch.object(client._client.chat.completions, "create", return_value=mock_response):
            result = await client.chat_with_json_output(
                "system", "user",
                output_schema={"type": "object"},
            )
            assert isinstance(result, dict), f"Expected dict, got {type(result)}"
