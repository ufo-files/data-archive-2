import os
import unittest
from unittest import mock

from build_archive_count import github_headers


class GithubHeadersTests(unittest.TestCase):
    def test_uses_workflow_token_for_api_requests(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "test-token"}, clear=True):
            headers = github_headers()

        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(headers["X-GitHub-Api-Version"], "2022-11-28")

    def test_allows_unauthenticated_local_use(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            headers = github_headers()

        self.assertNotIn("Authorization", headers)


if __name__ == "__main__":
    unittest.main()
