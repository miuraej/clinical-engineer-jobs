import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('crawl', Path(__file__).resolve().parent / 'crawl.py')
crawl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawl)


class ExtractionTests(unittest.TestCase):
    def test_era_range_uses_end(self):
        result = crawl.extract('<main><h1>臨床工学技士 募集</h1><table><tr><th>受付期間</th><td>令和8年6月22日から令和8年7月31日まで</td></tr></table></main>')
        self.assertEqual(result['deadline'], '2026-07-31')

    def test_exam_date_is_not_deadline(self):
        result = crawl.extract('<main><h1>臨床工学技士 採用</h1><table><tr><th>試験日</th><td>2026年10月16日</td></tr></table></main>')
        self.assertIsNone(result['deadline'])

    def test_missing_year_is_not_guessed(self):
        self.assertEqual(crawl.dates_in('応募締切 9月25日'), [])

    def test_multiple_rounds_are_unknown(self):
        result = crawl.extract('<main><h1>臨床工学技士 募集</h1><dl><dt>応募締切</dt><dd>2026年8月1日</dd><dt>応募締切</dt><dd>2026年10月1日</dd></dl></main>')
        self.assertIsNone(result['deadline'])

    def test_navigation_is_not_a_job(self):
        result = crawl.extract('<nav>臨床工学技士 募集</nav><main><h1>看護師募集</h1></main>')
        self.assertFalse(result['relevant'])

    def test_unrelated_closed_link_does_not_close_job(self):
        result = crawl.extract('<main><h1>臨床工学技士募集</h1><a>看護師の募集は終了しました</a></main>')
        self.assertFalse(result['ended'])

    def test_robots_disallow(self):
        fetcher = crawl.Fetcher()
        parser = crawl.RobotFileParser()
        parser.parse(['User-agent: *', 'Disallow: /recruit/'])
        fetcher.rules['https://example.org'] = parser
        with self.assertRaisesRegex(RuntimeError, 'robots_disallowed'):
            fetcher.get('https://example.org/recruit/ce.html')

    def test_failure_keeps_confirmation_time(self):
        # Integration of the real output path with a fake network, restored afterward.
        from unittest.mock import patch
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = {'id':'a','hospital':'A病院','prefecture':'東京都','url':'https://a.test/recruit/ce'}
            source2 = {'id':'b','hospital':'B病院','prefecture':'東京都','url':'https://b.test/recruit/ce'}
            (root / 'sources.json').write_text(json.dumps([source,source2]), encoding='utf-8')
            output=root / 'jobs.json'
            output.write_text(json.dumps({'jobs':[{'id':crawl.job_id(source['url']), 'url':source['url'], 'last_checked':'2026-01-01T00:00:00+09:00','status':'listed'}]}),encoding='utf-8')
            def fake_get(_, url):
                if url == source['url']:
                    raise RuntimeError('robots_disallowed')
                return '<main><h1>臨床工学技士 募集</h1></main>'
            with patch.object(crawl,'ROOT',root), patch.object(crawl.Fetcher,'get',fake_get):
                crawl.main()
            result=json.loads(output.read_text(encoding='utf-8'))['jobs'][0]
            self.assertEqual(result['last_checked'],'2026-01-01T00:00:00+09:00')
            self.assertEqual(result['status'],'unknown')


if __name__ == '__main__':
    unittest.main()
