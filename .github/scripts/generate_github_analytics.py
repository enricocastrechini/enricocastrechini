from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets' / 'github-analytics'
OUT.mkdir(parents=True, exist_ok=True)
USERNAME = 'enricocastrechini'
UA = 'copilot-agent'

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


def fetch(url: str) -> str:
    req = Request(url, headers={'User-Agent': UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def plural(value: int, unit: str) -> str:
    return f"{value} {unit}{'' if value == 1 else 's'}"


def extract_contribution_days(html_text: str) -> list[tuple[date, int]]:
    day_ids = []
    for tag in re.findall(r'<td\b[^>]*class="ContributionCalendar-day"[^>]*>', html_text, re.S):
        date_match = re.search(r'data-date="([0-9-]+)"', tag)
        id_match = re.search(r'id="([^"]+)"', tag)
        if date_match and id_match:
            day_ids.append((date_match.group(1), id_match.group(1)))

    tooltip_counts = {}
    for tag, label in re.findall(r'(<tool-tip\b[^>]*>)([^<]+)</tool-tip>', html_text, re.S):
        id_match = re.search(r'for="([^"]+)"', tag)
        if not id_match:
            continue
        label = html.unescape(label.strip())
        match = re.match(r'([0-9,]+) contributions? on ', label)
        tooltip_counts[id_match.group(1)] = int(match.group(1).replace(',', '')) if match else 0

    days = []
    for day_str, day_id in day_ids:
        days.append((datetime.strptime(day_str, '%Y-%m-%d').date(), tooltip_counts.get(day_id, 0)))
    days.sort()
    return days


def summarize_contributions(days: list[tuple[date, int]], start: date, end: date) -> dict:
    if not days:
        raise RuntimeError('Could not parse any contribution days from the GitHub contributions page.')

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


def parse_contributions() -> dict:
    today = date.today()
    start = today - timedelta(days=364)
    html_text = fetch(f'https://github.com/users/{USERNAME}/contributions?from={start.isoformat()}&to={today.isoformat()}')
    days = extract_contribution_days(html_text)
    return summarize_contributions(days, start, today)


def svg_wrap(width: int, height: int, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n<title>GitHub analytics snapshot for {USERNAME}</title>\n<desc>Static snapshot generated from public GitHub profile data and refreshed by workflow.</desc>\n<defs>\n  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n    <stop offset="0%" stop-color="{BG}"/>\n    <stop offset="100%" stop-color="#111827"/>\n  </linearGradient>\n</defs>\n<rect width="100%" height="100%" rx="18" fill="url(#bg)"/>\n{body}\n</svg>'''


def text(x, y, content, size=16, fill=TEXT, weight='400', anchor='start'):
    content = html.escape(str(content))
    return f'<text x="{x}" y="{y}" fill="{fill}" font-family="Segoe UI, Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{content}</text>'


def streak_svg(contrib):
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


def activity_svg(contrib):
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


def main() -> None:
    contrib = parse_contributions()
    (OUT / 'streak.svg').write_text(streak_svg(contrib))
    (OUT / 'activity.svg').write_text(activity_svg(contrib))


if __name__ == '__main__':
    main()
