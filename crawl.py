"""Allowlisted, bounded recruitment-page crawler. No search-engine scraping."""
import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
AGENT = 'ClinicalEngineerJobsBot'
USER_AGENT = AGENT + '/1.0 (+https://github.com/miuraej/clinical-engineer-jobs)'
MAX_BYTES = 2_000_000
MAX_LINKS = 6
KEYWORD = re.compile(r'臨床工学技[士師]')
LABEL = re.compile(r'応募締|募集締|提出期限|申込.*期限|申込.*期間|受付期間|応募期間')


def normalize(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip()


def dates_in(text):
    text = normalize(text)
    text = re.sub(r'(令和|平成)(元|\d+)年', lambda m: str((2018 if m[1] == '令和' else 1988) + (1 if m[2] == '元' else int(m[2]))) + '年', text)
    values = []
    for match in re.finditer(r'((?:19|20)\d{2})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})(?:日)?', text):
        try:
            values.append(date(*map(int, match.groups())).isoformat())
        except ValueError:
            pass
    return values


def extract(html):
    soup = BeautifulSoup(html, 'html.parser')
    for item in soup.select('script, style, nav, header, footer, noscript'):
        item.decompose()
    scope = soup.select_one('main, article, #main, #content') or soup
    text = normalize(scope.get_text(' ', strip=True))
    headings = [normalize(x.get_text(' ', strip=True)) for x in scope.select('h1, h2, h3')]
    title = next((x for x in headings if KEYWORD.search(x)), '臨床工学技士 採用情報')
    # Only explicit deadline fields; never infer a deadline from a test/hiring date.
    fields = []
    for row in scope.select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) >= 2 and LABEL.search(normalize(cells[0].get_text(' ', strip=True))):
            fields.append(normalize(' '.join(c.get_text(' ', strip=True) for c in cells[1:])))
    for key in scope.select('dt'):
        if LABEL.search(normalize(key.get_text(' ', strip=True))):
            value = key.find_next_sibling('dd')
            if value:
                fields.append(normalize(value.get_text(' ', strip=True)))
    # Heading-style deadline sections, capped at the next heading.
    for heading in scope.select('h2, h3, h4'):
        if LABEL.fullmatch(normalize(heading.get_text(' ', strip=True))):
            lines = []
            for sibling in heading.next_siblings:
                if getattr(sibling, 'name', '') in ['h1', 'h2', 'h3', 'h4']:
                    break
                lines.append(sibling.get_text(' ', strip=True) if hasattr(sibling, 'get_text') else str(sibling))
            fields.append(normalize(' '.join(lines)))
    # Multiple rounds and ambiguous fields need manual confirmation, not a guessed date.
    parsed = [dates_in(value) for value in fields]
    deadlines = {values[-1] for values in parsed if values}
    deadline = next(iter(deadlines)) if len(deadlines) == 1 else None
    employment = '公式ページで確認'
    for word in ['任期付', '非常勤', 'パート', '正規職員', '正職員', '常勤']:
        if word in title or word in text[:2500]:
            employment = word
            break
    ended = any(re.search(r'(募集|受付|応募).{0,10}(終了しました|締め切りました|締切りました|終了しました。)', x) for x in headings)
    return {'title': title[:140], 'deadline': deadline,
            'deadline_note': '複数日程あり・公式ページで確認' if len(deadlines) > 1 else ('随時受付・公式ページで確認' if any(re.search(r'随時|定員', x) for x in fields) and not deadline else '公式ページで確認'),
            'employment': employment, 'ended': ended,
            'relevant': bool(KEYWORD.search(text) and re.search(r'募集|採用|応募', text))}


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # No following redirects to unreviewed domains or paths without checking robots.
        raise RuntimeError('redirect_requires_review')


class Fetcher:
    def __init__(self):
        self.rules = {}
        self.last_request = {}
        self.opener = build_opener(SafeRedirect())

    def raw(self, url, delay=3):
        host = urlsplit(url).netloc
        time.sleep(max(0, delay - (time.monotonic() - self.last_request.get(host, 0))))
        self.last_request[host] = time.monotonic()
        with self.opener.open(Request(url, headers={'User-Agent': USER_AGENT}), timeout=25) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise RuntimeError('response_too_large')
            return body, response.headers.get_content_charset(), response.headers.get_content_type()

    def get(self, url):
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.username or parts.password:
            raise RuntimeError('invalid_url')
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.rules:
            parser = RobotFileParser()
            try:
                body, _, _ = self.raw(origin + '/robots.txt')
                parser.parse(body.decode('utf-8', errors='replace').splitlines())
            except HTTPError as error:
                if error.code not in (404, 410):
                    raise RuntimeError('robots_unavailable') from error
                parser.parse([])
            except Exception as error:
                raise RuntimeError('robots_unavailable') from error
            self.rules[origin] = parser
        rules = self.rules[origin]
        if not rules.can_fetch(AGENT, url):
            raise RuntimeError('robots_disallowed')
        delay = max(3, rules.crawl_delay(AGENT) or rules.crawl_delay('*') or 0)
        rate = rules.request_rate(AGENT) or rules.request_rate('*')
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        if delay > 60:
            raise RuntimeError('crawl_delay_requires_review')
        body, charset, content_type = self.raw(url, delay)
        if content_type not in ('text/html', 'application/xhtml+xml'):
            raise RuntimeError('unsupported_content_type')
        if not charset:
            match = re.search(br'charset=["\x27]?([\w-]+)', body[:4096], re.I)
            charset = match[1].decode('ascii') if match else 'utf-8'
        return body.decode(charset, errors='replace')


def job_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def main():
    sources = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
    output = ROOT / 'jobs.json'
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {'jobs': []}
    old = {j['id']: j for j in previous['jobs']}
    now = datetime.now(JST)
    stamp = now.isoformat(timespec='seconds')
    fetcher = Fetcher()
    jobs, reports, visited = [], [], set()

    def collect(source, url, html=None):
        if url in visited:
            return
        visited.add(url)
        ident = job_id(url)
        try:
            data = extract(html if html is not None else fetcher.get(url))
            if not data.pop('relevant'):
                raise RuntimeError('no_recruitment_content')
            ended = data.pop('ended')
            status = 'ended' if ended or (data['deadline'] and data['deadline'] < now.date().isoformat()) else 'listed'
            jobs.append({**data, 'id': ident, 'source_id': source['id'], 'hospital': source['hospital'],
                         'prefecture': source['prefecture'], 'url': url, 'status': status,
                         'last_checked': stamp, 'last_attempt': stamp, 'fetch_status': 'ok',
                         'first_seen': old.get(ident, {}).get('first_seen', stamp)})
            reports.append({'source_id': source['id'], 'hospital': source['hospital'], 'url': url, 'status': 'ok', 'checked_at': stamp})
        except Exception as error:
            reason = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            reports.append({'source_id': source['id'], 'hospital': source['hospital'], 'url': url, 'status': 'error', 'reason': reason, 'checked_at': stamp})
            if ident in old:
                prior = dict(old[ident])
                prior.update(last_attempt=stamp, fetch_status='error', status='unknown')
                jobs.append(prior)

    for source in sources:
        if source.get('mode') != 'index':
            collect(source, source['url'])
            continue
        try:
            html = fetcher.get(source['url'])
            soup = BeautifulSoup(html, 'html.parser')
            links = []
            for a in soup.select('a[href]'):
                text = normalize(a.get_text(' ', strip=True))
                url = urldefrag(urljoin(source['url'], a['href']))[0]
                if KEYWORD.search(text) and re.search(r'募集|採用', text) and urlsplit(url).netloc == urlsplit(source['url']).netloc and '/recruit/' in urlsplit(url).path and url != source['url'] and not url.lower().endswith('.pdf') and url not in links:
                    links.append(url)
            reports.append({'source_id': source['id'], 'hospital': source['hospital'], 'url': source['url'], 'status': 'ok', 'checked_at': stamp, 'discovered': len(links)})
            for link in links[:MAX_LINKS]:
                collect(source, link)
        except Exception as error:
            reports.append({'source_id': source['id'], 'hospital': source['hospital'], 'url': source['url'], 'status': 'error', 'reason': type(error).__name__, 'checked_at': stamp})
    # Preserve vanished index entries as unconfirmed. Never silently delete history.
    for ident, prior in old.items():
        if ident not in {job['id'] for job in jobs}:
            prior = dict(prior)
            prior.update(status='unknown', fetch_status='not_seen', last_attempt=stamp)
            jobs.append(prior)
    result = {'schema_version': 1, 'generated_at': datetime.now(JST).isoformat(timespec='seconds'), 'source_count': len(sources), 'jobs': jobs, 'sources': reports}
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, output)
    successes = sum(r['status'] == 'ok' for r in reports)
    print(f'Checked: {successes}/{len(reports)}; entries: {len(jobs)}')
    for report in reports:
        if report['status'] != 'ok':
            print(f"WARNING {report['hospital']}: {report.get('reason', 'error')}")
    if not successes:
        raise SystemExit('No sources could be checked; do not publish this run.')


if __name__ == '__main__':
    main()
