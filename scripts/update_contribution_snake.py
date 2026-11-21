#!/usr/bin/env python3
"""Render a game of Snake over the public GitHub contribution calendar."""

import argparse
import calendar
import random
from collections import deque
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


COLORS = ("#272937", "#31594d", "#438571", "#6eb698", "#a4efc7")
FOOD_COLOR = "#beff68"
SNAKE_COLORS = ("#83ef89", "#5bdd72", "#50cf67", "#48bf60", "#43af59", "#3b9f54", "#348e4b", "#307f44")
PITCH = 14
STEP_SECONDS = 0.14
MEALS_PER_LOOP = 30
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))


class ContributionCalendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            attributes = dict(attrs)
            if "data-date" in attributes and "data-level" in attributes:
                self.days[date.fromisoformat(attributes["data-date"])] = int(attributes["data-level"])


def contribution_days(owner):
    parser = ContributionCalendar()
    url = f"https://github.com/users/{quote(owner, safe='')}/contributions"
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "Merunex-profile-calendar"})
    with urlopen(request, timeout=20) as response:
        parser.feed(response.read().decode("utf-8"))

    today = datetime.now(timezone.utc).date()
    if not parser.days or max(parser.days) < today - timedelta(days=1):
        raise ValueError("GitHub did not return a current public contribution calendar")
    cutoff = max(parser.days) - timedelta(days=364)
    days = {day: level for day, level in sorted(parser.days.items()) if day >= cutoff}
    if len(days) != 365 or any(not 0 <= level < len(COLORS) for level in days.values()):
        raise ValueError("GitHub returned an incomplete or invalid contribution calendar")
    return days


def neighbors(cell, directions=DIRECTIONS):
    x, y = cell
    return ((x + dx, y + dy) for dx, dy in directions)


def meal_path(cells, body, rng):
    """Pick a reachable food tile and vary how equally short paths are explored."""
    directions = list(DIRECTIONS)
    rng.shuffle(directions)
    head = body[0]
    open_cells = cells.difference(body)
    queue = deque([head])
    previous = {head: None}
    depths = {head: 0}
    candidates = []
    while queue:
        cell = queue.popleft()
        depth = depths[cell]
        if depth >= 5:
            candidates.append(cell)
        if depth == 17:
            continue
        for neighbor in neighbors(cell, directions):
            if neighbor in open_cells and neighbor not in previous:
                queue.append(neighbor)
                previous[neighbor] = cell
                depths[neighbor] = depth + 1

    rng.shuffle(candidates)
    for food in candidates:
        path = []
        cell = food
        while cell != head:
            path.append(cell)
            cell = previous[cell]
        size = min(len(body) + 1, len(SNAKE_COLORS))
        landing_body = (tuple(path) + body)[:size]
        if sum(cell in cells and cell not in landing_body for cell in neighbors(food)) >= 2:
            return list(reversed(path))
    return []


def play_snake(cells, seed):
    rng = random.Random(seed)
    starts = [cell for cell in sorted(cells) if all((cell[0] - i, cell[1]) in cells for i in range(4))]
    x, y = rng.choice(starts)
    body = tuple((x - i, y) for i in range(4))
    frames = [body]
    meals = []
    for _ in range(MEALS_PER_LOOP):
        path = meal_path(cells, body, rng)
        if not path:
            break
        spawn = len(frames) - 1 + (rng.randint(1, 3) if meals else 0)
        for step, cell in enumerate(path, start=1):
            size = len(body)
            if step == len(path) and size < len(SNAKE_COLORS):
                size += 1
            body = (cell,) + body[:size - 1]
            frames.append(body)
        meals.append((path[-1], spawn, len(frames) - 1))
    return frames, meals


def center(cell):
    week, row = cell
    return 22 + PITCH * week, 36 + PITCH * row


def draw_calendar(days, seed=None):
    first_day, last_day = min(days), max(days)
    sunday = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid = {day: divmod((day - sunday).days, 7) for day in days}
    width = center(grid[last_day])[0] + 22
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="155" viewBox="0 0 {width} 155" role="img" aria-labelledby="title description">
<title id="title">Contribution snake</title>
<desc id="description">Public GitHub contributions from {first_day} to {last_day}.</desc>
<style>text {{ font: 11px system-ui, sans-serif; fill: #c4c4d1; }}</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="154" rx="12" fill="#141622" stroke="#313347"/>''']

    label_days = sorted(day for day in days if day.day == 1)
    if grid[label_days[0]][0] >= 2:
        label_days.insert(0, first_day)
    for day in label_days:
        x, _ = center(grid[day])
        parts.append(f'<text x="{x - 5}" y="20">{calendar.month_abbr[day.month]}</text>')

    for day, level in sorted(days.items()):
        x, y = center(grid[day])
        parts.append(f'<rect x="{x - 5.5}" y="{y - 5.5}" width="11" height="11" rx="2.6" fill="{COLORS[level]}"/>')

    if seed is not None:
        frames, meals = play_snake(set(grid.values()), seed)
        parts.extend(draw_game(frames, meals))
    parts.append(f'''<path d="M16 128H{width - 16}" stroke="#303244"/>
<rect x="16" y="137" width="9" height="9" rx="2" fill="{COLORS[3]}"/>
<text x="31" y="145">Contributions</text>''')
    if seed is not None:
        parts.append(f'''<rect x="132" y="137" width="9" height="9" fill="{FOOD_COLOR}"/>
<text x="147" y="145">Snake food</text>''')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def draw_game(frames, meals):
    duration = len(frames) * STEP_SECONDS
    timing = f'calcMode="discrete" dur="{duration:.3f}s" repeatCount="indefinite"'
    parts = []

    for cell, spawn, bite in meals:
        x, y = center(cell)
        if spawn == 0:
            keys, values = f"0;{bite / len(frames):.6f};1", "1;0;0"
        else:
            keys = f"0;{spawn / len(frames):.6f};{bite / len(frames):.6f};1"
            values = "0;1;0;0"
        parts.append(f'''<g class="food" transform="translate({x} {y})" opacity="0">
  <rect x="-5" y="-5" width="10" height="10" fill="{FOOD_COLOR}"/>
  <rect x="-3" y="-3" width="3" height="3" fill="#f2ffd0"/>
  <animate attributeName="opacity" values="{values}" keyTimes="{keys}" {timing}/>
</g>''')

    angles = []
    for head, neck, *_ in frames:
        direction = (head[0] - neck[0], head[1] - neck[1])
        angles.append(str(DIRECTIONS.index(direction) * 90))
    facing = f'<animateTransform attributeName="transform" type="rotate" values="{";".join(angles)}" {timing}/>'

    parts.append('<g class="snake">')
    for index in reversed(range(len(frames[-1]))):
        cells = (frame[min(index, len(frame) - 1)] for frame in frames)
        positions = ";".join(f"{x} {y}" for x, y in map(center, cells))
        parts.append(f'''<g class="{'head' if index == 0 else 'body'}" transform="translate({positions.split(';', 1)[0]})">
  <rect x="-6" y="-6" width="12" height="12" fill="{SNAKE_COLORS[index]}"/>
  <animateTransform attributeName="transform" type="translate" values="{positions}" {timing}/>''')
        if index == 0:
            parts.append(f'''<g class="eyes">
  <rect x="1" y="-4" width="2" height="2" fill="#142a1b"/>
  <rect x="1" y="2" width="2" height="2" fill="#142a1b"/>
  {facing}
</g>''')
        parts.append("</g>")
    parts.append("</g>")
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    args = parser.parse_args()
    days = contribution_days(args.owner)
    assets = Path(__file__).resolve().parents[1] / "assets"
    seed = f"{args.owner}:{max(days)}"
    (assets / "contribution-snake.svg").write_text(draw_calendar(days, seed), encoding="utf-8")
    (assets / "contribution-calendar.svg").write_text(draw_calendar(days), encoding="utf-8")
    print(f"Rendered {len(days)} public calendar days with a new Snake game for {max(days)}")


if __name__ == "__main__":
    main()
