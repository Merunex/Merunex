#!/usr/bin/env python3
"""Render a game of Snake over the public GitHub contribution calendar."""

import argparse
import calendar
import random
import re
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


COLORS = ("#272937", "#31594d", "#438571", "#6eb698", "#a4efc7")
FOOD_COLOR = "#beff68"
ACTIVITY_COLOR = "#8ee8c8"
BODY_COLOR = "#48bd65"
HEAD_COLOR = "#a5f497"
PITCH = 14
STEP_SECONDS = 0.12
FOOD_ON_BOARD = 24
RESULT_PAUSE = 16
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))
Cell = tuple[int, int]


@dataclass
class SnakeRound:
    heads: list[Cell]
    start_neck: Cell
    body_events: dict[Cell, list[tuple[int, int]]]
    food_events: dict[Cell, list[tuple[int, int]]]
    activity_bites: dict[Cell, int]
    won: bool


class ContributionCalendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}
        self.counts = {}
        self.active_ids = {}
        self.tooltip_day = None
        self.tooltip_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            attributes = dict(attrs)
            if "data-date" in attributes and "data-level" in attributes:
                day = date.fromisoformat(attributes["data-date"])
                level = int(attributes["data-level"])
                self.days[day] = level
                if level and "id" in attributes:
                    self.active_ids[attributes["id"]] = day
        elif tag == "tool-tip":
            self.tooltip_day = self.active_ids.get(dict(attrs).get("for"))
            self.tooltip_text = []

    def handle_data(self, data):
        if self.tooltip_day is not None:
            self.tooltip_text.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.tooltip_day is not None:
            label = "".join(self.tooltip_text).strip()
            match = re.match(r"([0-9,]+) contributions?\b", label)
            if match:
                self.counts[self.tooltip_day] = int(match[1].replace(",", ""))
            self.tooltip_day = None


def contribution_days(owner):
    parser = ContributionCalendar()
    url = f"https://github.com/users/{quote(owner, safe='')}/contributions"
    request = Request(url, headers={
        "Accept": "text/html", "Accept-Language": "en-US", "User-Agent": "Merunex-profile-calendar",
    })
    with urlopen(request, timeout=20) as response:
        parser.feed(response.read().decode("utf-8"))

    today = datetime.now(timezone.utc).date()
    if not parser.days or max(parser.days) < today - timedelta(days=1):
        raise ValueError("GitHub did not return a current public contribution calendar")
    cutoff = max(parser.days) - timedelta(days=364)
    days = {day: level for day, level in sorted(parser.days.items()) if day >= cutoff}
    if len(days) != 365 or any(not 0 <= level < len(COLORS) for level in days.values()):
        raise ValueError("GitHub returned an incomplete or invalid contribution calendar")
    active = {day for day, level in days.items() if level}
    total = sum(parser.counts[day] for day in active) if active <= parser.counts.keys() else None
    return days, total


def board_cycle(weeks, mirror, rng):
    """Join the square circuits along a random spanning tree to visit the whole board."""
    links = {}

    def connect_path(*cells):
        for first, second in zip(cells, cells[1:]):
            links.setdefault(first, set()).add(second)
            links.setdefault(second, set()).add(first)

    def disconnect(first, second):
        links[first].remove(second)
        links[second].remove(first)

    blocks = {(col, row) for col in range(weeks // 2) for row in range(3)}
    for col, row in blocks:
        x, y = 1 + 2 * col, 1 + 2 * row
        connect_path((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1), (x, y))

    pending = [(0, 0)]
    blocks.remove((0, 0))
    while pending:
        col, row = pending.pop()
        x, y = 1 + 2 * col, 1 + 2 * row
        for dx, dy in rng.sample(DIRECTIONS, len(DIRECTIONS)):
            neighbor = col + dx, row + dy
            if neighbor not in blocks:
                continue
            blocks.remove(neighbor)
            pending.append(neighbor)
            if dx:
                edge_x = x + int(dx > 0)
                first, second = (edge_x, y), (edge_x, y + 1)
            else:
                edge_y = y + int(dy > 0)
                first, second = (x, edge_y), (x + 1, edge_y)
            across_first = first[0] + dx, first[1] + dy
            across_second = second[0] + dx, second[1] + dy
            disconnect(first, second)
            disconnect(across_first, across_second)
            connect_path(first, across_first)
            connect_path(second, across_second)

    # The top and left borders add two cells at a time, keeping the corner open.
    for x in range(1, weeks, 2):
        disconnect((x, 1), (x + 1, 1))
        connect_path((x, 1), (x, 0), (x + 1, 0), (x + 1, 1))
    for y in range(1, 7, 2):
        disconnect((1, y), (1, y + 1))
        connect_path((1, y), (0, y), (0, y + 1), (1, y + 1))

    start = (1, 0)
    previous, current = None, start
    cycle = []
    for _ in range(len(links)):
        cycle.append(current)
        previous, current = current, min(links[current] - {previous})
    if current != start or len(set(cycle)) != len(links):
        raise ValueError("The snake route must visit each board cell exactly once")
    if mirror:
        cycle = [(weeks - 1 - x, 6 - y) for x, y in cycle]
    if rng.choice((False, True)):
        cycle.reverse()
    return cycle


def play_snake(weeks, mirror, activity, seed):
    rng = random.Random(seed)
    cycle = board_cycle(weeks, mirror, rng)
    capacity = len(cycle)
    clear_starts = [
        index for index in range(capacity)
        if all(cycle[(index + offset) % capacity] not in activity for offset in range(-3, 1))
    ]
    position = rng.choice(clear_starts or range(capacity))
    body = deque(cycle[(position + offset) % capacity] for offset in range(-3, 1))
    occupied = set(body)
    board = set(cycle)
    remaining = activity - occupied
    activity_bites = dict.fromkeys(activity & occupied, 0)
    body_events = {cell: [(0, int(cell in occupied))] for cell in cycle}
    heads, start_neck = [body[-1]], body[-2]

    food = set()
    food_events = {}

    def refill_food(frame):
        missing = FOOD_ON_BOARD - len(food)
        if not missing:
            return
        free_cells = sorted(board - occupied - remaining - food)
        for cell in rng.sample(free_cells, min(missing, len(free_cells))):
            food.add(cell)
            events = food_events.setdefault(cell, [(0, 0)] if frame else [])
            events.append((frame, 1))

    refill_food(0)
    while len(body) < capacity:
        position = (position + 1) % capacity
        target = cycle[position]
        if target in occupied:
            break
        frame = len(heads)
        heads.append(target)
        if target in remaining:
            remaining.remove(target)
            activity_bites[target] = frame
        elif target in food:
            food.remove(target)
            food_events[target].append((frame, 0))
        else:
            tail = body.popleft()
            occupied.remove(tail)
            body_events[tail].append((frame, 0))
        body.append(target)
        occupied.add(target)
        body_events[target].append((frame, 1))
        refill_food(frame)

    return SnakeRound(heads, start_neck, body_events, food_events, activity_bites, len(body) == capacity)


def center(cell):
    week, row = cell
    return 22 + PITCH * week, 36 + PITCH * row


def draw_calendar(days, seed=None):
    first_day, last_day = min(days), max(days)
    sunday = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid = {day: divmod((day - sunday).days, 7) for day in days}
    weeks = grid[last_day][0] + 1
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
        date_cells = set(grid.values())
        activity = {grid[day] for day, level in days.items() if level}
        game = play_snake(weeks, (0, 0) in date_cells, activity, seed)
        for cell in sorted(game.body_events.keys() - date_cells):
            x, y = center(cell)
            parts.append(f'<rect x="{x - 5.5}" y="{y - 5.5}" width="11" height="11" rx="2.6" fill="#1d1f2c"/>')
        parts.extend(draw_game(game, activity, width))
    parts.append(f'''<path d="M16 128H{width - 16}" stroke="#303244"/>
<rect x="16" y="137" width="9" height="9" rx="2" fill="{COLORS[3]}"/>
<text x="31" y="145">Contributions</text>''')
    if seed is not None:
        parts.append(f'''<rect x="132" y="137" width="9" height="9" fill="{FOOD_COLOR}"/>
<text x="147" y="145">Snake food</text>''')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def draw_game(game, activity, width):
    end_frame = len(game.heads) - 1
    frames = len(game.heads) + RESULT_PAUSE
    duration = frames * STEP_SECONDS
    timing = f'calcMode="discrete" dur="{duration:.3f}s" repeatCount="indefinite"'

    def timeline(events):
        events = [*events, (frames, events[-1][1])]
        keys = ";".join(f"{at / frames:.6f}" for at, _ in events)
        values = ";".join(str(value) for _, value in events)
        return f'keyTimes="{keys}" values="{values}" {timing}'

    def opacity(events):
        if len(events) < 2:
            return ""
        return f'<animate attributeName="opacity" {timeline(events)}/>'

    def translation(events):
        positions = []
        for frame, cell in events:
            x, y = center(cell)
            positions.append((frame, f"{x} {y}"))
        return f'<animateTransform attributeName="transform" type="translate" {timeline(positions)}/>'

    parts = ['<g class="activity-food">']
    for cell in sorted(activity):
        bite = game.activity_bites.get(cell)
        if bite == 0:
            continue
        x, y = center(cell)
        marker = opacity([(0, 1), (bite, 0)]) if bite is not None else ""
        parts.append(f'<rect x="{x - 2}" y="{y - 2}" width="4" height="4" fill="{ACTIVITY_COLOR}">{marker}</rect>')
    parts.append("</g>")

    parts.append(f'''<defs><g id="food-square">
  <rect x="-5" y="-5" width="10" height="10" fill="{FOOD_COLOR}"/>
  <rect x="-3" y="-3" width="3" height="3" fill="#f2ffd0"/>
</g></defs>
<g class="food">''')
    for cell, events in sorted(game.food_events.items()):
        x, y = center(cell)
        parts.append(f'<use href="#food-square" x="{x}" y="{y}" opacity="{events[0][1]}">{opacity(events)}</use>')
    parts.append("</g>")

    parts.append('<g class="snake">')
    for cell, events in sorted(game.body_events.items()):
        x, y = center(cell)
        parts.append(f'''<rect class="body-cell" x="{x - 6}" y="{y - 6}" width="12" height="12"
  fill="{BODY_COLOR}" opacity="{events[0][1]}">{opacity(events)}</rect>''')

    angles = []
    neck = game.start_neck
    for frame, head in enumerate(game.heads):
        direction = head[0] - neck[0], head[1] - neck[1]
        angle = DIRECTIONS.index(direction) * 90
        if not angles or angle != angles[-1][1]:
            angles.append((frame, angle))
        neck = head
    start_x, start_y = center(game.heads[0])
    result = "Board cleared" if game.won else "Game over"
    parts.append(f'''<g class="head" transform="translate({start_x} {start_y})">
  <rect x="-6" y="-6" width="12" height="12" fill="{HEAD_COLOR}"/>
  {translation(enumerate(game.heads))}
  <g class="eyes">
    <rect x="1" y="-4" width="2" height="2" fill="#142a1b"/>
    <rect x="1" y="2" width="2" height="2" fill="#142a1b"/>
    <animateTransform attributeName="transform" type="rotate" {timeline(angles)}/>
  </g>
</g>
</g>
<text class="game-result" x="{width - 17}" y="145" text-anchor="end" opacity="0"
  style="fill: {HEAD_COLOR}; font-weight: 600">{result}{opacity([(0, 0), (end_frame, 1)])}</text>''')
    return parts


def update_readme(path, active_days, total):
    start = "<!-- contribution-summary:start -->"
    end = "<!-- contribution-summary:end -->"
    before, start_marker, tail = path.read_text(encoding="utf-8").partition(start)
    _, end_marker, after = tail.partition(end)
    if not start_marker or not end_marker:
        raise ValueError("The contribution summary markers are missing from README.md")
    days = f"{active_days:,} active {'day' if active_days == 1 else 'days'}"
    if total is None:
        summary = days
    else:
        contributions = f"{total:,} {'contribution' if total == 1 else 'contributions'}"
        summary = f"{contributions} across {days}"
    path.write_text(f"{before}{start}\n**{summary}** in the last 365 days.\n{end}{after}", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    args = parser.parse_args()
    days, total = contribution_days(args.owner)
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    seed = f"{args.owner}:{max(days)}"
    (assets / "contribution-snake-game.svg").write_text(draw_calendar(days, seed), encoding="utf-8")
    (assets / "contribution-calendar.svg").write_text(draw_calendar(days), encoding="utf-8")
    active = sum(level > 0 for level in days.values())
    update_readme(root / "README.md", active, total)
    print(f"Rendered {len(days)} public calendar days, including {active} active days")


if __name__ == "__main__":
    main()
