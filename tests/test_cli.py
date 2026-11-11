import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pr_radar.cli import fetch_prs, main, summarize


class FakeResponse:
    def __init__(self, data):
        self.content = io.BytesIO(json.dumps(data).encode())

    def __enter__(self):
        return self.content

    def __exit__(self, *args):
        return False


class RadarTests(unittest.TestCase):
    def test_summary(self):
        prs = [
            {"number": 1, "title": "Old", "html_url": "https://github.com/x/y/pull/1", "draft": True, "updated_at": "2026-01-01T00:00:00Z"},
            {"number": 2, "title": "New", "html_url": "https://github.com/x/y/pull/2", "draft": False, "updated_at": "2026-01-19T00:00:00Z"},
        ]
        output = summarize(prs, days=14, now=datetime(2026, 1, 20, tzinfo=timezone.utc))
        self.assertEqual(output["draft"], 1)
        self.assertEqual(output["stale_count"], 1)
        self.assertEqual(output["stale"][0]["number"], 1)

    @patch("pr_radar.github.urlopen")
    def test_fetch_public_api(self, mock_open):
        mock_open.return_value = FakeResponse([{"number": 1}])
        result = fetch_prs("owner/repo", limit=10)
        self.assertEqual(result, [{"number": 1}])
        request = mock_open.call_args.args[0]
        self.assertIn("/repos/owner/repo/pulls?", request.full_url)
        self.assertNotIn("Authorization", request.headers)

    @patch("pr_radar.github.urlopen")
    def test_auth_header(self, mock_open):
        mock_open.return_value = FakeResponse([])
        fetch_prs("owner/repo", token="secret")
        self.assertEqual(mock_open.call_args.args[0].headers["Authorization"], "Bearer secret")

    def test_invalid_repo(self):
        with self.assertRaises(ValueError):
            fetch_prs("invalid")

    def test_negative_days(self):
        with self.assertRaises(ValueError):
            summarize([], days=-1)

    @patch("pr_radar.cli.fetch_prs", return_value=[])
    def test_json_cli(self, fetch):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["owner/repo", "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())["total"], 0)


if __name__ == "__main__":
    unittest.main()
