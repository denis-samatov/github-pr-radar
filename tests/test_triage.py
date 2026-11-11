import io
import json
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from pr_radar.cli import main
from pr_radar.github import GitHubClient, fetch_prs
from pr_radar.report import ci_signal, enrich, markdown, review_signal, summarize
from test_cli import FakeResponse


def pr(number=1, **kwargs):
    return dict(number=number, title='Fix | <script> [link]', html_url=f'https://github.com/x/y/pull/{number}',
                updated_at='2020-01-01T00:00:00Z', user={'login': 'Denis'}, labels=[{'name': 'bug'}],
                head={'sha': 'abc123'}, **kwargs)


class PaginationTests(unittest.TestCase):
    @patch('pr_radar.github.urlopen')
    def test_partial_final_page_has_no_duplicate_offset(self, open_url):
        def respond(request, **kwargs):
            query = parse_qs(urlparse(request.full_url).query)
            size, page = int(query['per_page'][0]), int(query['page'][0])
            return FakeResponse([{'number': n} for n in range((page-1)*size, page*size)])
        open_url.side_effect = respond
        rows = fetch_prs('x/y', limit=150)
        self.assertEqual([row['number'] for row in rows], list(range(150)))
        self.assertEqual(open_url.call_count, 2)

    @patch('pr_radar.github.urlopen')
    def test_keyed_pagination(self, open_url):
        open_url.side_effect = [FakeResponse({'check_runs': [{'id': n} for n in range(100)]}),
                                FakeResponse({'check_runs': [{'id': 100}]})]
        self.assertEqual(len(GitHubClient().items('/test', key='check_runs')), 101)

    @patch('pr_radar.github.urlopen')
    def test_bad_payload(self, open_url):
        open_url.return_value = FakeResponse({'message': 'bad'})
        with self.assertRaises(ValueError):
            fetch_prs('x/y')

    def test_repository_cannot_inject_paths_or_queries(self):
        for repo in ['x/..', 'x/y?token=foo', 'x/y/z', 'x/y z', '/y']:
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                fetch_prs(repo)


class SignalTests(unittest.TestCase):
    def test_reviewer_latest_decision_and_dismissal(self):
        def review(id, user, state):
            return {'id': id, 'user': {'login': user}, 'state': state}
        rows = [review(1, 'a', 'CHANGES_REQUESTED'), review(2, 'a', 'APPROVED'), review(3, 'a', 'COMMENTED')]
        self.assertEqual(review_signal(rows), 'approval_present')
        rows.append(review(4, 'b', 'CHANGES_REQUESTED'))
        self.assertEqual(review_signal(rows), 'changes_requested')
        rows.extend([review(5, 'b', 'DISMISSED'), review(6, 'a', 'DISMISSED')])
        self.assertEqual(review_signal(rows), 'no_decisive_review')

    def test_ci_aggregation(self):
        check = lambda conclusion: {'status': 'completed', 'conclusion': conclusion}
        self.assertEqual(ci_signal([], []), 'no_checks')
        self.assertEqual(ci_signal([check('success'), check('skipped')], []), 'passed')
        self.assertEqual(ci_signal([check(None)], []), 'unknown')
        self.assertEqual(ci_signal([{'status': 'queued'}], []), 'pending')
        self.assertEqual(ci_signal([check('failure'), {'status': 'queued'}], []), 'failed')
        self.assertEqual(ci_signal([], [{'context': 'a', 'state': 'success'}, {'context': 'a', 'state': 'failure'}]), 'passed')
        self.assertEqual(ci_signal([check('success')], [{'context': 'a', 'state': 'error'}]), 'failed')

    def test_partial_access_keeps_review_and_unknown_ci(self):
        client = Mock()
        client.items.side_effect = [[{'user': {'login': 'a'}, 'state': 'APPROVED'}],
                                    HTTPError('https://api.github.com', 403, 'Forbidden', {}, None)]
        report = summarize([pr()])
        enrich(report, [pr()], 'x/y', client)
        item = report['pull_requests'][0]
        self.assertEqual(item['ci'], 'unknown')
        self.assertEqual(item['review'], 'approval_present')
        self.assertEqual(report['warnings'], 1)
        self.assertEqual(report['stale'][0]['ci'], 'unknown')

    def test_draft_and_closed_do_not_suggest_review(self):
        client = Mock()
        client.items.return_value = []
        rows = [pr(1, draft=True), pr(2, state='closed')]
        report = summarize(rows)
        enrich(report, rows, 'x/y', client)
        self.assertEqual([item['actions'] for item in report['pull_requests']], [['draft'], ['closed']])

    def test_exact_stale_boundary_and_future_timestamp(self):
        now = datetime(2020, 1, 15, tzinfo=timezone.utc)
        self.assertEqual(summarize([pr()], 14, now)['stale_count'], 1)
        self.assertEqual(summarize([pr()], 15, now)['stale_count'], 0)
        self.assertEqual(summarize([pr()], 0, datetime(2019, 1, 1, tzinfo=timezone.utc))['pull_requests'][0]['days_since_update'], 0)


class CliTests(unittest.TestCase):
    @patch('pr_radar.cli.fetch_prs')
    def test_combined_filters_and_exit_code(self, fetch):
        fetch.return_value = [pr(), pr(2, draft=True), {**pr(3), 'labels': []}]
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            code = main(['x/y', '--author', 'denis', '--label', 'bug', '--exclude-drafts', '--json', '--fail-on-stale'])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(report['scanned'], 3)
        self.assertEqual(report['total'], 1)

    @patch('pr_radar.cli.fetch_prs', return_value=[])
    def test_empty_report_exit(self, fetch):
        with patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['x/y', '--fail-on-stale']), 0)

    @patch('pr_radar.cli.fetch_prs')
    def test_auth_error_does_not_leak_exception(self, fetch):
        fetch.side_effect = HTTPError('https://example.com/secret', 401, 'secret', {}, None)
        with patch('sys.stderr', new_callable=io.StringIO) as error:
            self.assertEqual(main(['x/y']), 1)
        self.assertNotIn('secret', error.getvalue())
        self.assertIn('Authentication failed', error.getvalue())

    @patch('pr_radar.cli.fetch_prs')
    def test_validate_before_network(self, fetch):
        for flags in [['--stale-days', '-1'], ['--limit', '0']]:
            with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                main(['x/y', *flags])
            self.assertEqual(error.exception.code, 2)
        fetch.assert_not_called()

    @patch('pr_radar.cli.fetch_prs', return_value=[pr()])
    def test_default_has_no_detail_requests(self, fetch):
        with patch('pr_radar.cli.enrich') as enrich_mock, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['x/y']), 0)
        enrich_mock.assert_not_called()

    def test_markdown_escapes_title(self):
        report = {'scanned': 1, **summarize([pr()])}
        text = markdown('x/y', report)
        self.assertIn('\\|', text)
        self.assertIn('\\<script\\>', text)
        self.assertIn('https://github.com/x/y/pull/1', text)
        self.assertIn('not_requested', text)


if __name__ == '__main__':
    unittest.main()
