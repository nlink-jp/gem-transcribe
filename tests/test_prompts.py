"""Tests for gem_transcribe.llm.prompts."""

from __future__ import annotations

import re

import pytest

from gem_transcribe.llm.prompts import (
    JSON_SHAPE,
    SYSTEM_INSTRUCTION,
    build_user_prompt,
)


class TestSpeakerBlock:
    def test_no_hints_attempts_name_inference_with_letter_fallback(self) -> None:
        prompt = build_user_prompt(languages=["en"], speaker_hints=None)
        # Letter fallback still mentioned
        assert "Speaker A" in prompt
        assert "Speaker B" in prompt
        # Name inference instructions are present
        assert "infer" in prompt.lower()
        assert "self-introduction" in prompt.lower()
        # No leakage of hint-style language
        assert "participants are present" not in prompt

    def test_no_hints_warns_against_inventing_names(self) -> None:
        prompt = build_user_prompt(languages=["en"], speaker_hints=None)
        # Defensive instruction: don't fabricate names
        assert "never invent a name" in prompt.lower()

    def test_hints_wrapped_in_nonce_tag(self) -> None:
        prompt = build_user_prompt(languages=["en"], speaker_hints=["Yamada", "Sato"])
        assert "Yamada, Sato" in prompt
        # Tag uses speaker_hints_<hex> format
        assert re.search(r"<speaker_hints_[a-f0-9]{32}>", prompt)
        assert re.search(r"</speaker_hints_[a-f0-9]{32}>", prompt)

    def test_hints_with_each_call_use_fresh_nonce(self) -> None:
        p1 = build_user_prompt(languages=["en"], speaker_hints=["A"])
        p2 = build_user_prompt(languages=["en"], speaker_hints=["A"])
        # Tag nonce should differ between calls (fresh Tag.new each time)
        nonce1 = re.search(r"<speaker_hints_([a-f0-9]{32})>", p1)
        nonce2 = re.search(r"<speaker_hints_([a-f0-9]{32})>", p2)
        assert nonce1 and nonce2
        assert nonce1.group(1) != nonce2.group(1)


class TestLanguageBlock:
    def test_single_language(self) -> None:
        prompt = build_user_prompt(languages=["ja"], speaker_hints=None)
        assert '"ja"' in prompt
        # Single-language wording should not promise multiple keys
        assert "every requested language" not in prompt

    def test_multiple_languages_lists_each(self) -> None:
        prompt = build_user_prompt(languages=["en", "ja"], speaker_hints=None)
        assert '"en"' in prompt
        assert '"ja"' in prompt
        assert "every requested language" in prompt

    def test_empty_languages_rejected(self) -> None:
        with pytest.raises(ValueError, match="language"):
            build_user_prompt(languages=[], speaker_hints=None)


class TestPromptComposition:
    def test_includes_json_shape(self) -> None:
        prompt = build_user_prompt(languages=["en"], speaker_hints=None)
        assert JSON_SHAPE.split("\n")[0] in prompt

    def test_system_instruction_constant(self) -> None:
        # Smoke test: keep the system instruction stable enough for the LLM
        # to anchor on "JSON" output.
        assert "JSON" in SYSTEM_INSTRUCTION
        assert "transcrib" in SYSTEM_INSTRUCTION.lower()
