from __future__ import annotations

import html
import json
import os
import textwrap
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets' / 'github-analytics'
OUT.mkdir(parents=True, exist_ok=True)
USERNAME = os.environ.get('GITHUB_USERNAME', 'enricocastrechini')
API_URL = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
GRAPHQL_URL = os.environ.get('GITHUB_GRAPHQL_URL', f'{API_URL}/graphql')
UA = 'copilot-agent'
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
PINNED_REPOS = [
    ('enricocastrechini', 'BAC-Mammography-Detection-CVD'),
]

BG = '#1a1b27'
CARD = '#24283b'
MUTED = '#565f89'
TEXT = '#c0caf5'
ACCENT = '#7aa2f7'
ACCENT2 = '#bb9af7'
ACCENT3 = '#73daca'
ACCENT4 = '#f7768e'
GRID = '#2f3549'
LEVELS = ['#1f2335', '#2f3549', '#3b4261', '#7aa2f7', '#73daca']
LANGUAGE_SWATCHES = [ACCENT, ACCENT2, ACCENT3, ACCENT4, '#e0af68', '#9ece6a']
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


def build_headers(token: str, *, content_type: str | None = None) -> dict[str, str]:
    headers = {
        'User-Agent': UA,
        'Accept': 'application/vnd.github+json',
        'Authorization': 'Bearer ' + token,
    }
    if content_type:
        headers['Content-Type'] = content_type
    return headers


def get_github_token() -> str:
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        return token
    raise RuntimeError('Missing GitHub token. Set GITHUB_TOKEN or GH_TOKEN before running the analytics generator.')


def shorten_api_error(detail: str) -> str:
    detail = detail.strip()
    if not detail:
        return 'No error body was returned by GitHub.'
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return detail.splitlines()[0][:240]
    message = payload.get('message') or payload.get('error') or detail
    errors = payload.get('errors')
    if isinstance(errors, list) and errors:
        nested = []
        for item in errors:
            if isinstance(item, dict):
                nested.append(item.get('message') or item.get('code') or json.dumps(item, sort_keys=True))
            else:
                nested.append(str(item))
        message = f"{message} ({'; '.join(nested)})"
    return str(message)


def format_rate_limit_message(headers: dict[str, str], message: str) -> str | None:
    if headers.get('X-RateLimit-Remaining') != '0':
        return None
    reset = headers.get('X-RateLimit-Reset')
    if reset:
        try:
            reset_time = datetime.fromtimestamp(int(reset), tz=UTC).strftime('%Y-%m-%d %H:%M UTC')
            return f'{message} Rate limit resets at {reset_time}.'
        except ValueError:
            pass
    return message


def request_json(url: str, token: str, *, method: str = 'GET', payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = build_headers(token, content_type='application/json' if payload is not None else None)
    for attempt in range(MAX_RETRIES):
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode('utf-8', errors='replace'))
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            status = exc.code
            if status in RETRYABLE_HTTP_STATUSES and attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
                continue
            if status in {401, 403}:
                rate_limit_message = format_rate_limit_message(
                    dict(exc.headers.items()),
                    f'GitHub API rate limit exceeded while requesting {url}.',
                )
                if rate_limit_message:
                    raise RuntimeError(rate_limit_message) from exc
                raise RuntimeError(
                    f'GitHub API request to {url} failed with HTTP {status}. '
                    f'{shorten_api_error(body)} Ensure the token can read public profile and repository data.'
                ) from exc
            raise RuntimeError(
                f'GitHub API request to {url} failed with HTTP {status}. {shorten_api_error(body)}'
            ) from exc
        except URLError as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f'GitHub API request to {url} failed: {exc.reason}') from exc

    raise RuntimeError(f'GitHub API request to {url} failed after {MAX_RETRIES} attempts.')


def graphql_request(query: str, variables: dict[str, object], token: str) -> dict:
    payload = request_json(GRAPHQL_URL, token, method='POST', payload={'query': query, 'variables': variables})
    errors = payload.get('errors')
    if errors:
        message = '; '.join(error.get('message', 'Unknown GraphQL error') for error in errors)
        if 'rate limit' in message.lower():
            raise RuntimeError(f'GitHub GraphQL query hit the rate limit. {message}')
        raise RuntimeError(f'GitHub GraphQL query failed. {message}')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise RuntimeError('GitHub GraphQL query returned an unexpected payload without data.')
    return data


def plural(value: int, unit: str) -> str:
    return f"{value} {unit}{'' if value == 1 else 's'}"


def format_compact(value: int) -> str:
    if value < 1000:
        return str(value)
    if value < 10_000:
        return f'{value / 1000:.1f}K'
    if value < 1_000_000:
        return f'{round(value / 1000):.0f}K'
    return f'{value / 1_000_000:.1f}M'


def wrap_label(value: str, width: int) -> list[str]:
    text_value = ' '.join(str(value).split())
    if not text_value:
        return ['']
    return textwrap.wrap(text_value, width=width, break_long_words=False, break_on_hyphens=False) or ['']


def flatten_contribution_calendar(weeks: list[dict], start: date, end: date) -> list[tuple[date, int]]:
    days = []
    for week in weeks:
        for day_info in week.get('contributionDays', []):
            day = date.fromisoformat(day_info['date'])
            if start <= day <= end:
                days.append((day, int(day_info.get('contributionCount', 0))))
    days.sort()
    return days


def summarize_contributions(days: list[tuple[date, int]], start: date, end: date) -> dict:
    if not days:
        raise RuntimeError('Could not parse any contribution days from the GitHub contribution calendar.')

    counts_by_day = {day: count for day, count in days}
    full_days = []
    cursor = start
    while cursor <= end:
        full_days.append((cursor, counts_by_day.get(cursor, 0)))
        cursor += timedelta(days=1)

    total = sum(count for _, count in full_days)
    if full_days[-1][1] > 0:
        current = 0
        for _, count in reversed(full_days):
            if count > 0:
                current += 1
            else:
                break
    else:
        current = 0

    longest = 0
    running = 0
    best_end = None
    for day, count in full_days:
        if count > 0:
            running += 1
            if running > longest:
                longest = running
                best_end = day
        else:
            running = 0

    active_days = sum(1 for _, count in full_days if count > 0)
    peak = max((count for _, count in full_days), default=0)
    return {
        'days': full_days,
        'range_label': f'{start.isoformat()} → {end.isoformat()}',
        'total': total,
        'current_streak': current,
        'longest_streak': longest,
        'active_days': active_days,
        'peak_day': peak,
        'best_end': best_end,
        'current_longest_is_ongoing': bool(current and current == longest),
    }


def fetch_contributions(token: str) -> dict:
    today = date.today()
    start = today - timedelta(days=364)
    query = '''
    query ContributionCalendar($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    '''
    data = graphql_request(
        query,
        {
            'username': USERNAME,
            'from': f'{start.isoformat()}T00:00:00Z',
            'to': f'{today.isoformat()}T23:59:59Z',
        },
        token,
    )
    user = data.get('user')
    if not user:
        raise RuntimeError(f'GitHub user {USERNAME} was not found by the GraphQL API.')
    calendar = user['contributionsCollection']['contributionCalendar']
    days = flatten_contribution_calendar(calendar['weeks'], start, today)
    summary = summarize_contributions(days, start, today)
    summary['total'] = int(calendar.get('totalContributions', summary['total']))
    return summary


def fetch_user_profile(username: str, token: str) -> dict:
    return request_json(f'{API_URL}/users/{username}', token)


def fetch_owned_repositories(username: str, token: str) -> list[dict]:
    page = 1
    repositories = []
    while True:
        items = request_json(
            f'{API_URL}/users/{username}/repos?per_page=100&type=owner&sort=updated&page={page}',
            token,
        )
        if not isinstance(items, list):
            raise RuntimeError('GitHub repositories API returned an unexpected payload.')
        repositories.extend(items)
        if len(items) < 100:
            return repositories
        page += 1


def fetch_search_total_count(query: str, token: str) -> int:
    payload = request_json(f'{API_URL}/search/issues?q={quote_plus(query)}&per_page=1', token)
    return int(payload.get('total_count', 0))


def fetch_repository(owner: str, name: str, token: str) -> dict:
    return request_json(f'{API_URL}/repos/{owner}/{name}', token)


def fetch_repository_languages(owner: str, name: str, token: str) -> dict[str, int]:
    payload = request_json(f'{API_URL}/repos/{owner}/{name}/languages', token)
    return {language: int(size) for language, size in payload.items()}


def build_profile_snapshot(token: str) -> tuple[dict, list[dict]]:
    user = fetch_user_profile(USERNAME, token)
    repositories = fetch_owned_repositories(USERNAME, token)
    pinned = []
    for owner, name in PINNED_REPOS:
        repo = fetch_repository(owner, name, token)
        repo['language_breakdown'] = fetch_repository_languages(owner, name, token)
        pinned.append(repo)

    profile = {
        'followers': int(user.get('followers', 0)),
        'public_repos': int(user.get('public_repos', 0)),
        'total_stars': sum(int(repo.get('stargazers_count', 0)) for repo in repositories),
        'merged_prs': fetch_search_total_count(f'author:{USERNAME} is:pr is:merged', token),
        'closed_issues': fetch_search_total_count(f'author:{USERNAME} is:issue is:closed', token),
        'years_active': max(1, date.today().year - date.fromisoformat(user['created_at'][:10]).year + 1),
    }
    return profile, pinned


def build_language_stats(language_breakdown: dict[str, int], primary_language: str | None) -> tuple[str, float | None, list[dict]]:
    ordered = sorted(language_breakdown.items(), key=lambda item: item[1], reverse=True)
    total = sum(size for _, size in ordered)
    selected_primary = primary_language or (ordered[0][0] if ordered else 'Unknown')
    if total == 0:
        return selected_primary, None, []
    primary_size = language_breakdown.get(selected_primary)
    if primary_size is None and ordered:
        selected_primary, primary_size = ordered[0]
    share = (primary_size / total * 100) if primary_size is not None else None
    stats = []
    for index, (name, size) in enumerate(ordered[:4]):
        stats.append({
            'name': name,
            'share': size / total * 100,
            'color': LANGUAGE_SWATCHES[index % len(LANGUAGE_SWATCHES)],
        })
    return selected_primary, share, stats


def svg_wrap(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
        f'<title>GitHub analytics snapshot for {USERNAME}</title>\n'
        '<desc>Static snapshot generated from authenticated GitHub profile data and refreshed by workflow.</desc>\n'
        '<defs>\n'
        '  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n'
        f'    <stop offset="0%" stop-color="{BG}"/>\n'
        '    <stop offset="100%" stop-color="#111827"/>\n'
        '  </linearGradient>\n'
        '</defs>\n'
        '<rect width="100%" height="100%" rx="18" fill="url(#bg)"/>\n'
        f'{body}\n'
        '</svg>'
    )


def text(x, y, content, size=16, fill=TEXT, weight='400', anchor='start'):
    content = html.escape(str(content))
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{content}</text>'
    )


def multiline_text(x: int, y: int, lines: list[str], *, size: int = 13, fill: str = TEXT, weight: str = '400', line_height: int = 18) -> str:
    escaped = ''.join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}">{escaped}</text>'
    )


def streak_svg(contrib: dict) -> str:
    highlight = f"{plural(contrib['current_streak'], 'day')} current streak"
    if contrib['longest_streak'] and contrib['current_longest_is_ongoing']:
        secondary = f"Longest streak: {plural(contrib['longest_streak'], 'day')} • ongoing"
    elif contrib['longest_streak'] and contrib['best_end']:
        secondary = f"Longest streak: {plural(contrib['longest_streak'], 'day')} • ended {contrib['best_end'].isoformat()}"
    else:
        secondary = 'No contribution streak detected yet'
    stats = [
        ('Active days', contrib['active_days']),
        ('Peak day', contrib['peak_day']),
        ('Current streak', contrib['current_streak']),
        ('Longest streak', contrib['longest_streak']),
    ]
    body = [text(24, 34, 'Streak Snapshot', 22, weight='700'), text(24, 58, highlight, 14, ACCENT2, '700'), text(24, 78, secondary, 12, MUTED)]
    for i, (label, value) in enumerate(stats):
        x = 24 + (i % 2) * 282
        y = 104 + (i // 2) * 100
        body.append(f'<rect x="{x}" y="{y}" width="270" height="84" rx="14" fill="{CARD}" stroke="{GRID}"/>')
        body.append(text(x + 18, y + 30, label, 13, MUTED, '600'))
        body.append(text(x + 18, y + 60, value, 24, [ACCENT, ACCENT2, ACCENT3, ACCENT4][i], '700'))
    body.append(f'<rect x="24" y="308" width="552" height="48" rx="14" fill="{CARD}" stroke="{GRID}"/>')
    body.append(text(42, 338, f"{contrib['total']} contributions in the last 365 days", 16, TEXT, '600'))
    body.append(text(576, 338, contrib['range_label'], 11, MUTED, '400', 'end'))
    return svg_wrap(600, 400, '\n'.join(body))


def activity_svg(contrib: dict) -> str:
    days = contrib['days']
    min_date = min(day for day, _ in days)
    start_sunday = min_date - timedelta(days=(min_date.weekday() + 1) % 7)
    cell = 8
    gap = 2
    x0 = 28
    y0 = 86
    body = [text(24, 34, 'Contribution Activity Snapshot', 22, weight='700'), text(24, 58, 'Last 365 days of public contributions', 12, MUTED)]
    month_positions = {}
    for day, _ in days:
        col = (day - start_sunday).days // 7
        month_positions.setdefault(day.strftime('%Y-%m'), (day.strftime('%b'), col))
    for month, col in list(month_positions.values())[:12]:
        x = min(576, x0 + col * (cell + gap))
        body.append(text(x, 78, month, 10, MUTED))
    for idx, label in zip([0, 2, 4], ['Sun', 'Tue', 'Thu']):
        body.append(text(4, y0 + idx * (cell + gap) + 8, label, 10, MUTED))
    for day, count in days:
        col = (day - start_sunday).days // 7
        row = (day.weekday() + 1) % 7
        level = 0 if count == 0 else 1 if count < 2 else 2 if count < 4 else 3 if count < 7 else 4
        x = x0 + col * (cell + gap)
        y = y0 + row * (cell + gap)
        body.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{LEVELS[level]}"/>')
    legend_x = 416
    body.append(text(legend_x, 364, 'Less', 10, MUTED))
    for i, color in enumerate(LEVELS):
        body.append(f'<rect x="{legend_x + 28 + i * 14}" y="355" width="10" height="10" rx="2" fill="{color}"/>')
    body.append(text(legend_x + 110, 364, 'More', 10, MUTED))
    body.append(text(24, 386, f"Current streak {contrib['current_streak']} • Longest streak {contrib['longest_streak']} • {contrib['range_label']}", 11, MUTED))
    return svg_wrap(600, 400, '\n'.join(body))


def trophies_svg(profile: dict, contrib: dict) -> str:
    trophies = [
        ('Contributions', format_compact(contrib['total']), 'last 365 days', ACCENT),
        ('Longest streak', plural(contrib['longest_streak'], 'day'), 'best run', ACCENT2),
        ('Active days', format_compact(contrib['active_days']), 'days with activity', ACCENT3),
        ('Public repos', format_compact(profile['public_repos']), 'owned repositories', ACCENT4),
        ('Followers', format_compact(profile['followers']), 'GitHub audience', '#e0af68'),
        ('Merged PRs', format_compact(profile['merged_prs']), 'authored and merged', '#9ece6a'),
    ]
    body = [
        text(24, 34, 'Profile Milestones', 22, weight='700'),
        text(24, 58, f"{format_compact(profile['total_stars'])} stars • {profile['closed_issues']} closed issues • active since {profile['years_active']} year{'s' if profile['years_active'] != 1 else ''}", 12, MUTED),
    ]
    for index, (label, value, subtitle, color) in enumerate(trophies):
        x = 24 + (index % 3) * 184
        y = 88 + (index // 3) * 112
        body.append(f'<rect x="{x}" y="{y}" width="168" height="92" rx="14" fill="{CARD}" stroke="{GRID}"/>')
        body.append(f'<circle cx="{x + 24}" cy="{y + 24}" r="8" fill="{color}"/>')
        body.append(text(x + 40, y + 29, label, 13, MUTED, '600'))
        body.append(text(x + 18, y + 60, value, 24, color, '700'))
        body.append(text(x + 18, y + 80, subtitle, 11, MUTED))
    body.append(f'<rect x="24" y="318" width="552" height="38" rx="12" fill="{CARD}" stroke="{GRID}"/>')
    body.append(text(42, 343, f"Current streak {contrib['current_streak']} • Peak day {contrib['peak_day']} contributions", 13, TEXT, '600'))
    return svg_wrap(600, 380, '\n'.join(body))


def pinned_repos_svg(repositories: list[dict]) -> str:
    card_height = 184
    top = 78
    gap = 18
    height = top + len(repositories) * card_height + max(len(repositories) - 1, 0) * gap + 30
    body = [
        text(24, 34, 'Featured Repositories', 22, weight='700'),
        text(24, 58, 'Repo-owned snapshot refreshed from authenticated GitHub metadata', 12, MUTED),
    ]
    for index, repo in enumerate(repositories):
        x = 24
        y = top + index * (card_height + gap)
        name = repo.get('full_name', repo.get('name', 'Repository'))
        description_lines = wrap_label(repo.get('description') or 'No description provided.', 64)[:3]
        primary_language, primary_share, language_stats = build_language_stats(
            repo.get('language_breakdown', {}),
            repo.get('language'),
        )
        share_label = f'{primary_share:.1f}%' if primary_share is not None else 'n/a'
        body.append(f'<rect x="{x}" y="{y}" width="552" height="{card_height}" rx="16" fill="{CARD}" stroke="{GRID}"/>')
        body.append(text(x + 20, y + 30, name, 20, ACCENT, '700'))
        body.append(multiline_text(x + 20, y + 54, description_lines, size=12, fill=TEXT, line_height=17))
        bar_x = x + 20
        bar_y = y + 108
        bar_width = 512
        body.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="12" rx="6" fill="{BG}" stroke="{GRID}"/>')
        cursor = 0.0
        for stat in language_stats:
            width = bar_width * stat['share'] / 100
            if width <= 0:
                continue
            body.append(f'<rect x="{bar_x + cursor:.2f}" y="{bar_y}" width="{width:.2f}" height="12" rx="6" fill="{stat["color"]}"/>')
            cursor += width
        body.append(text(x + 20, y + 138, f'Primary language: {primary_language} • {share_label} of tracked bytes', 13, ACCENT2, '600'))
        body.append(text(x + 20, y + 162, f"★ {repo.get('stargazers_count', 0)}   ⑂ {repo.get('forks_count', 0)}", 12, MUTED, '600'))
        legend_x = x + 268
        for stat in language_stats[:3]:
            body.append(f'<circle cx="{legend_x}" cy="{y + 158}" r="4" fill="{stat["color"]}"/>')
            body.append(text(legend_x + 10, y + 162, f"{stat['name']} {stat['share']:.1f}%", 11, MUTED))
            legend_x += 108
    return svg_wrap(600, height, '\n'.join(body))


def write_assets(contrib: dict, profile: dict, pinned: list[dict]) -> None:
    (OUT / 'streak.svg').write_text(streak_svg(contrib))
    (OUT / 'activity.svg').write_text(activity_svg(contrib))
    (OUT / 'trophies.svg').write_text(trophies_svg(profile, contrib))
    (OUT / 'pinned-repos.svg').write_text(pinned_repos_svg(pinned))


def main() -> None:
    token = get_github_token()
    contrib = fetch_contributions(token)
    profile, pinned = build_profile_snapshot(token)
    write_assets(contrib, profile, pinned)


if __name__ == '__main__':
    main()
