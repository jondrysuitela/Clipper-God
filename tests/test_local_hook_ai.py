"""Tests for optional, local-only Ollama hook analysis."""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from clippergod.core.models import Word
from clippergod.pipeline.local_hook_ai import (
    MAX_TRANSCRIPT_CHARS,
    HookAnalysis,
    InvalidEndpointError,
    ModelUnavailableError,
    OllamaConfig,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    analyze_hook,
    rank_hooks,
    review_transcript,
)


class _Response:
    def __init__(self, value):
        self._data = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._data


def _tags(*models):
    return {"models": [{"name": name} for name in models]}


def _chat(content):
    return {"message": {"content": content}, "done": True}


class TestLocalHookAI(unittest.TestCase):
    def setUp(self):
        self.config = OllamaConfig(model="test-model")

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_success_checks_tags_and_returns_validated_analysis(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat('{"score": 82.5, "reasons": ["Clear question"]}')),
        ]
        build_opener.return_value = opener

        result = analyze_hook("Why does this work?", self.config)

        self.assertEqual(result, HookAnalysis(82.5, ("Clear question",)))
        self.assertEqual(opener.open.call_count, 2)
        tags_request = opener.open.call_args_list[0].args[0]
        chat_request = opener.open.call_args_list[1].args[0]
        self.assertEqual(tags_request.full_url, "http://127.0.0.1:11434/api/tags")
        self.assertEqual(chat_request.full_url, "http://127.0.0.1:11434/api/chat")
        chat_payload = json.loads(chat_request.data)
        self.assertEqual(chat_payload["format"]["properties"]["score"]["maximum"], 100)
        self.assertFalse(chat_payload["format"]["additionalProperties"])

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_rank_hooks_scores_all_candidates_and_returns_best_first(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat(json.dumps({
                "candidates": [
                    {"id": "second", "score": 91, "reasons": ["Strong question"]},
                    {"id": "first", "score": 65, "reasons": ["Needs context"]},
                ],
            }))),
        ]
        build_opener.return_value = opener

        result = rank_hooks(
            [("first", "A transcript"), ("second", "Why did this happen?")],
            self.config,
        )

        self.assertEqual([candidate_id for candidate_id, _ in result], ["second", "first"])
        self.assertEqual(result[0][1], HookAnalysis(91.0, ("Strong question",)))
        payload = json.loads(opener.open.call_args_list[1].args[0].data)
        self.assertEqual(payload["format"]["properties"]["candidates"]["maxItems"], 24)
        self.assertIn("do not invent timestamps", payload["messages"][1]["content"])

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_rank_hooks_rejects_missing_candidate_result(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat(json.dumps({
                "candidates": [{"id": "first", "score": 65, "reasons": ["Reason"]}],
            }))),
        ]
        build_opener.return_value = opener

        with self.assertRaisesRegex(OllamaResponseError, "every supplied candidate"):
            rank_hooks([("first", "A"), ("second", "B")], self.config)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_rank_hooks_rejects_too_many_candidates_before_network(self, build_opener):
        with self.assertRaisesRegex(ValueError, "between 1 and 24"):
            rank_hooks([(str(i), "hook") for i in range(25)], self.config)
        build_opener.assert_not_called()

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_review_transcript_marks_differences_without_replacing_words(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat(json.dumps({"segments": [{
                "id": "0",
                "assessment": "possible_missed_words",
                "note": "The second transcript contains an extra phrase.",
            }]}))),
        ]
        build_opener.return_value = opener
        primary = [Word("kita", 0.1, 0.4), Word("pergi", 0.5, 0.9)]
        second = [
            Word("kita", 0.1, 0.4), Word("akan", 0.4, 0.6),
            Word("pergi", 0.6, 1.0),
        ]

        result = review_transcript(primary, second, self.config)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assessment"], "possible_missed_words")
        self.assertEqual(result[0]["primary"], "kita pergi")
        self.assertEqual(result[0]["second_pass"], "kita akan pergi")
        self.assertEqual(primary, [Word("kita", 0.1, 0.4), Word("pergi", 0.5, 0.9)])

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_review_transcript_skips_ollama_when_asr_text_matches(self, build_opener):
        words = [Word("Halo,", 0.1, 0.4), Word("dunia.", 0.5, 0.9)]

        result = review_transcript(words, list(words), self.config)

        self.assertEqual(result, [])
        build_opener.assert_not_called()

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_review_transcript_flags_an_empty_second_asr_pass(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat(json.dumps({"segments": [{
                "id": "0",
                "assessment": "possible_missed_words",
                "note": "The second transcript is empty.",
            }]}))),
        ]
        build_opener.return_value = opener

        result = review_transcript(
            [Word("ucapan", 0.1, 0.6)],
            [],
            self.config,
        )

        self.assertEqual(result[0]["second_pass"], "")
        self.assertEqual(result[0]["assessment"], "possible_missed_words")

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_review_transcript_rejects_unknown_segment_id(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat(json.dumps({"segments": [{
                "id": "unknown", "assessment": "no_clear_issue", "note": "Review it.",
            }]}))),
        ]
        build_opener.return_value = opener

        with self.assertRaisesRegex(OllamaResponseError, "invalid transcript review"):
            review_transcript(
                [Word("ini", 0.1, 0.4)],
                [Word("itu", 0.1, 0.4)],
                self.config,
            )

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_unavailable_server_has_clear_error(self, build_opener):
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("connection refused")
        build_opener.return_value = opener

        with self.assertRaisesRegex(OllamaUnavailableError, "could not contact local Ollama"):
            analyze_hook("A hook", self.config)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_timeout_has_clear_error(self, build_opener):
        opener = Mock()
        opener.open.side_effect = TimeoutError()
        build_opener.return_value = opener

        with self.assertRaises(OllamaTimeoutError):
            analyze_hook("A hook", self.config)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_missing_model_stops_before_chat(self, build_opener):
        opener = Mock()
        opener.open.return_value = _Response(_tags("another-model"))
        build_opener.return_value = opener

        with self.assertRaises(ModelUnavailableError):
            analyze_hook("A hook", self.config)
        self.assertEqual(opener.open.call_count, 1)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_malformed_model_output_is_rejected(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat('{"score": 101, "reasons": ["too high"]}')),
        ]
        build_opener.return_value = opener

        with self.assertRaisesRegex(OllamaResponseError, "0 to 100"):
            analyze_hook("A hook", self.config)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_non_json_model_output_is_rejected(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat("not JSON")),
        ]
        build_opener.return_value = opener

        with self.assertRaisesRegex(OllamaResponseError, "malformed"):
            analyze_hook("A hook", self.config)

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_transcript_is_sanitized_and_bounded(self, build_opener):
        opener = Mock()
        opener.open.side_effect = [
            _Response(_tags("test-model")),
            _Response(_chat('{"score": 50, "reasons": ["Adequate"]}')),
        ]
        build_opener.return_value = opener

        analyze_hook("  hi\x00\tthere  " + ("x" * (MAX_TRANSCRIPT_CHARS + 10)), self.config)

        payload = json.loads(opener.open.call_args_list[1].args[0].data)
        user_content = payload["messages"][1]["content"]
        transcript_sent = user_content.split("\n", 1)[1]
        self.assertNotIn("\x00", transcript_sent)
        self.assertEqual(len(transcript_sent), MAX_TRANSCRIPT_CHARS)
        self.assertTrue(transcript_sent.startswith("hi there"))

    @patch("clippergod.pipeline.local_hook_ai.urllib.request.build_opener")
    def test_non_local_endpoint_is_rejected_without_network(self, build_opener):
        config = OllamaConfig(model="test-model", endpoint="https://example.com")

        with self.assertRaises(InvalidEndpointError):
            analyze_hook("A hook", config)
        build_opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
