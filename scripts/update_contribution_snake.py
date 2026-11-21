#!/usr/bin/env python3
"""Render the public GitHub calendar and its successful deployment days."""

import argparse
import calendar
import json
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from itertools import count
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


API = "https://api.github.com"
COLORS = ("#272937", "#31594d", "#438571", "#6eb698", "#a4efc7")
GOLD = "#ffd080"
PITCH = 14
STEP_SECONDS = 0.085
START_SECONDS = 0.75
TAIL_LINK_SECONDS = 0.034
TAIL = ("#5d4d89", "#6f589c", "#8266af", "#9374bd", "#a384ce", "#b294dc", "#c1a5ef")


class ContributionCalendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            attributes = dict(attrs)
            if "data-date" in attributes and "data-level" in attributes:
                self.days[date.fromisoformat(attributes["data-date"])] = int(attributes["data-level"])


def read_public(url, accept):
    request = Request(url, headers={"Accept": accept, "User-Agent": "Merunex-profile-calendar"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def list_public(path, query=""):
    for page in count(1):
        url = f"{API}{path}?per_page=100&page={page}{query}"
        items = json.loads(read_public(url, "application/vnd.github+json"))
        if not isinstance(items, list):
            raise ValueError(f"Expected a list from {path}")
        yield from items
        if len(items) < 100:
            return


def contribution_days(owner):
    parser = ContributionCalendar()
    url = f"https://github.com/users/{quote(owner, safe='')}/contributions"
    parser.feed(read_public(url, "text/html"))

    today = datetime.now(timezone.utc).date()
    if not parser.days or max(parser.days) < today - timedelta(days=1):
        raise ValueError("GitHub did not return a current public contribution calendar")
    cutoff = max(parser.days) - timedelta(days=364)
    days = {day: level for day, level in sorted(parser.days.items()) if day >= cutoff}
    if len(days) != 365 or any(not 0 <= level < len(COLORS) for level in days.values()):
        raise ValueError("GitHub returned an incomplete or invalid contribution calendar")
    return days


def successful_deploy_days(owner, first_day, last_day):
    days = set()
    for repo in list_public(f"/users/{quote(owner, safe='')}/repos", "&type=owner"):
        if repo["private"]:
            continue
        repo_path = "/repos/" + quote(repo["full_name"], safe="/")
        for deployment in list_public(f"{repo_path}/deployments"):
            if date.fromisoformat(deployment["updated_at"][:10]) < first_day:
                continue
            path = f"{repo_path}/deployments/{deployment['id']}/statuses"
            for status in list_public(path):
                if status["state"] == "success":
                    day = date.fromisoformat(status["created_at"][:10])
                    if first_day <= day <= last_day:
                        days.add(day)
    return days


def route_cells(weeks, last_row):
    """Sweep the calendar from the newest week, alternating direction each column."""
    route = [(weeks - 1, row) for row in range(last_row, -1, -1)]
    for index, week in enumerate(range(weeks - 2, -1, -1)):
        rows = range(7) if index % 2 == 0 else range(6, -1, -1)
        route.extend((week, row) for row in rows)
    return route


def draw_calendar(days, deployments, animated=True):
    first_day, last_day = min(days), max(days)
    sunday = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid = {day: divmod((day - sunday).days, 7) for day in days}
    last_week, last_row = grid[last_day]

    def center(week, row):
        return (22 + PITCH * week, 36 + PITCH * row)

    route = route_cells(last_week + 1, last_row)
    arrival = {cell: START_SECONDS + index * STEP_SECONDS for index, cell in enumerate(route)}
    travel = (len(route) - 1) * STEP_SECONDS
    duration = START_SECONDS + travel + 1.2
    coords = " L".join(f"{x},{y}" for x, y in (center(*cell) for cell in route))
    width = center(last_week, 0)[0] + 22
    deploy_count = len(deployments)
    deploy_label = f"{deploy_count} deploy {'day' if deploy_count == 1 else 'days'}"
    route_definition = f'<path id="route" d="M{coords}"/>' if animated else ""
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="155" viewBox="0 0 {width} 155" role="img" aria-labelledby="title description">
<title id="title">Contribution snake</title>
<desc id="description">Public GitHub contributions from {first_day} to {last_day}. The snake eats gold cells on successful deployment days. {deploy_label}.</desc>
<style>text {{ font: 11px system-ui, sans-serif; fill: #c4c4d1; }}</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="154" rx="12" fill="#141622" stroke="#313347"/>
<defs>
  <g id="food">
    <rect x="-5.5" y="-5.5" width="11" height="11" rx="2.6" fill="{GOLD}"/>
    <path d="M0 -3 3 0 0 3 -3 0Z" fill="#795121"/>
  </g>
  {route_definition}
</defs>''']

    label_days = sorted(day for day in days if day.day == 1)
    if grid[label_days[0]][0] >= 2:
        label_days.insert(0, first_day)
    for day in label_days:
        x, _ = center(*grid[day])
        parts.append(f'<text x="{x - 5}" y="20">{calendar.month_abbr[day.month]}</text>')

    for day, level in sorted(days.items()):
        week, row = grid[day]
        x, y = center(week, row)
        color = COLORS[0 if day in deployments else level]
        parts.append(f'<rect x="{x - 5.5}" y="{y - 5.5}" width="11" height="11" rx="2.6" fill="{color}"/>')
        if day in deployments:
            parts.append(deployment_tile(x, y, arrival[(week, row)], duration, animated))

    if animated:
        parts.extend(draw_snake(travel, duration))
    parts.append(f'''<path d="M16 128H{width - 16}" stroke="#303244"/>
<rect x="16" y="137" width="9" height="9" rx="2" fill="{COLORS[3]}"/>
<text x="31" y="145">Contributions</text>
<use href="#food" x="132" y="141.5"/>
<text x="144" y="145">{deploy_label}</text>
</svg>''')
    return "\n".join(parts) + "\n"


def deployment_tile(x, y, bite, duration, animated):
    tile = f'<use class="deployment-day" href="#food" x="{x}" y="{y}"'
    if not animated:
        return tile + "/>"
    eaten = (bite + 0.16) / duration
    return tile + f'''>
  <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{bite / duration:.6f};{eaten:.6f};1"
    dur="{duration:.3f}s" repeatCount="indefinite"/>
</use>'''


def draw_snake(travel, duration):
    def motion(delay, rotate="0"):
        start = (START_SECONDS + delay) / duration
        end = (START_SECONDS + delay + travel) / duration
        return f'''<animateMotion dur="{duration:.3f}s" repeatCount="indefinite" rotate="{rotate}" calcMode="linear" keyPoints="0;0;1;1" keyTimes="0;{start:.6f};{end:.6f};1">
  <mpath href="#route"/>
</animateMotion>'''

    parts = ['<g class="snake">']
    for index, color in enumerate(TAIL):
        delay = (len(TAIL) - index) * TAIL_LINK_SECONDS
        parts.append(f'<circle r="{3 + index * 0.39:.2f}" fill="{color}">{motion(delay)}</circle>')
    parts.append(f'''<g>
  <path d="M5.5 0H10M9 0L11 -1.4M9 0L11 1.4" stroke="#ffb0c9" stroke-width="1.1" stroke-linecap="round" fill="none"/>
  <ellipse rx="7" ry="5.6" fill="#d7bcff" stroke="#201b2c" stroke-width="0.7"/>
  <circle cx="2.2" cy="-2.3" r="1.15" fill="#1d1830"/>
  <circle cx="2.2" cy="2.3" r="1.15" fill="#1d1830"/>
  {motion(0, "auto")}
</g>
</g>''')
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    args = parser.parse_args()
    days = contribution_days(args.owner)
    deployments = successful_deploy_days(args.owner, min(days), max(days))
    assets = Path(__file__).resolve().parents[1] / "assets"
    (assets / "contribution-snake.svg").write_text(draw_calendar(days, deployments), encoding="utf-8")
    (assets / "contribution-calendar.svg").write_text(
        draw_calendar(days, deployments, animated=False), encoding="utf-8"
    )
    print(f"Rendered {len(days)} public calendar days and {len(deployments)} successful deployment days")


if __name__ == "__main__":
    main()
