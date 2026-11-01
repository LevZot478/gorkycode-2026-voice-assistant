import json
import os
import unittest
from unittest.mock import Mock, patch

from ai.intent import _call_gigachat, _decode_intent, _get_gigachat_token, _GIGACHAT_TOKEN, parse_intent

SAMPLE = {
    "action": "create_task",
    "title": "Подготовить презентацию",
    "date_time": None,
    "period_start": None,
    "period_end": None,
    "query": None,
    "missing_fields": [],
    "kind": "task",
    "due_date": "2026-11-02",
}

class ProviderTests(unittest.TestCase):
    def setUp(self):
        _GIGACHAT_TOKEN.update(value=None, valid_until=0.0)

    def test_json_in_code_fence(self):
        value = "```json\n" + json.dumps(SAMPLE, ensure_ascii=False) + "\n```"
        self.assertEqual(_decode_intent(value), SAMPLE)

    def test_gigachat_oauth_and_completion(self):
        oauth = Mock(status_code=200)
        oauth.json.return_value = {"access_token": "test-bearer"}
        oauth.raise_for_status.return_value = None
        chat = Mock(status_code=200)
        chat.json.return_value = {"choices": [{"message": {"content": json.dumps(SAMPLE)}}]}
        chat.raise_for_status.return_value = None

        with patch.dict(os.environ, {"GIGACHAT_AUTH_KEY": "test-base64", "GIGACHAT_SCOPE": "GIGACHAT_API_PERS"}, clear=True):
            with patch("ai.intent.requests.post", side_effect=[oauth, chat]) as post:
                result = _call_gigachat([{"role": "user", "content": "test"}])
                self.assertEqual(json.loads(result)["action"], "create_task")
                self.assertEqual(post.call_count, 2)
                self.assertEqual(post.call_args_list[0].kwargs["headers"]["Authorization"], "Basic test-base64")
                self.assertEqual(post.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer test-bearer")
                self.assertIs(post.call_args_list[1].kwargs["verify"], True)

    def test_token_cached(self):
        oauth = Mock(status_code=200)
        oauth.json.return_value = {"access_token": "test-bearer"}
        with patch.dict(os.environ, {"GIGACHAT_AUTH_KEY": "test-base64"}, clear=True):
            with patch("ai.intent.requests.post", return_value=oauth) as post:
                self.assertEqual(_get_gigachat_token(), "test-bearer")
                self.assertEqual(_get_gigachat_token(), "test-bearer")
                self.assertEqual(post.call_count, 1)

    def test_no_key_in_production_does_not_try_localhost(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with patch("ai.intent.requests.post") as post:
                with self.assertRaisesRegex(RuntimeError, "GIGACHAT_AUTH_KEY"):
                    parse_intent("Создай задачу", "2026-11-01T15:00:00+03:00")
                post.assert_not_called()

if __name__ == "__main__":
    unittest.main()
