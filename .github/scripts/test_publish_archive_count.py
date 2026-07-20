import io
import json
import urllib.error
import unittest
from unittest import mock

from publish_archive_count import request_json


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.payload


def http_error(status):
    return urllib.error.HTTPError(
        "https://api.github.test/resource",
        status,
        "error",
        {},
        io.BytesIO(b"{}"),
    )


class RequestJsonTests(unittest.TestCase):
    def test_retries_transient_service_failure(self):
        urlopen = mock.Mock(side_effect=[http_error(503), FakeResponse({"ok": True})])
        sleep = mock.Mock()

        result = request_json(
            "https://api.github.test/resource",
            token="token",
            urlopen=urlopen,
            sleep=sleep,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_returns_none_for_allowed_not_found(self):
        result = request_json(
            "https://api.github.test/resource",
            token="token",
            allow_not_found=True,
            urlopen=mock.Mock(side_effect=http_error(404)),
            sleep=mock.Mock(),
        )

        self.assertIsNone(result)

    def test_does_not_retry_permanent_client_error(self):
        urlopen = mock.Mock(side_effect=http_error(403))
        sleep = mock.Mock()

        with self.assertRaises(urllib.error.HTTPError):
            request_json(
                "https://api.github.test/resource",
                token="token",
                urlopen=urlopen,
                sleep=sleep,
            )

        urlopen.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
