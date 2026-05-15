#!/usr/bin/env python3
"""Playwright-based client for https://edhpowerlevel.com/.

The site has no public scoring API: power-level / bracket calculation runs in
the browser (the Cloud Run backend only enriches card data). To get the
"recommended Commander Bracket" (y2 in the project's vocabulary) we drive the
real page with Chromium, paste a decklist, click *Analyze*, and scrape the
rendered result.

The single class :class:`EDHPowerLevelClient` is a context manager wrapping a
single Chromium context. Reuse it across many decks instead of creating a new
browser per request — startup cost dominates per-deck latency otherwise.
"""

from __future__ import annotations

import re
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from playwright.sync_api import (  # type: ignore[import-not-found]
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


EDHPL_URL = "https://edhpowerlevel.com/"

# Patterns that pick the numeric values out of the rendered page text. The
# layout uses emoji-prefixed headers (⚡ Power Level, ⚖️ Tipping Point, ...)
# followed by the value on the next visual line; in `inner_text("body")` they
# show up next to one another on the same line, which is what these regexes
# match. They are deliberately loose: if EDHPowerLevel rearranges sections, we
# want to keep extracting whatever still matches and fail loudly only on the
# bracket field.
RESULT_PATTERNS: Dict[str, re.Pattern[str]] = {
    "commander_bracket": re.compile(r"Commander Bracket[^0-9]{0,12}([1-5])"),
    "power_level": re.compile(r"Power Level\s*([0-9]+(?:\.[0-9]+)?\+?)\s*/\s*10"),
    "tipping_point": re.compile(r"Tipping Point\s*([0-9]+)"),
    "efficiency": re.compile(r"Efficiency\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10"),
    "impact": re.compile(r"Impact\s*([0-9]+(?:\.[0-9]+)?)"),
    "score": re.compile(r"Score\s*([0-9]+)\s*/\s*1000"),
    "average_playability": re.compile(r"Average Playability\s*([0-9]+(?:\.[0-9]+)?)%"),
}

# Cards the site couldn't resolve are listed under this header in the warning
# panel. We track them so failed lookups are visible in the processing log.
_NOT_LOADED_HEADER = re.compile(
    r"ERROR:\s*Not all card data was loaded.*?check your formatting[^\n]*\n+([\s\S]*?)(?:Analyze List|Reset All|\Z)",
    re.IGNORECASE,
)
_NOT_LOADED_LINE = re.compile(r"^\s*\d+\s+(.+?)\s*$", re.MULTILINE)


def decklist_text(mainboard: List[Dict[str, Any]]) -> str:
    """Build the multiline decklist string the site's textarea expects.

    The site accepts `<qty> <card name>` per line (MTGO / Archidekt syntax).
    Multiface cards use `Front // Back` (already the case in oracle_name).
    """
    lines: List[str] = []
    for row in mainboard or []:
        name = row.get("oracle_name")
        try:
            qty = int(row.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0
        if not name or qty <= 0:
            continue
        lines.append(f"{qty} {name}")
    return "\n".join(lines)


_FINGERPRINT_FIELDS = ("power_level", "score", "impact", "efficiency", "average_playability")


def _fingerprint(parsed: Dict[str, Any]) -> tuple:
    """Compact tuple of the scoring fields used to detect the pre-Analyze
    default page state (bracket=4 / pl=5.55 / score=447 / impact=516.00 /
    efficiency=4.82 / playability=51.8). Using five fields makes accidental
    collision with a real deck's computed result effectively impossible."""
    return tuple(parsed.get(field) for field in _FINGERPRINT_FIELDS)


def _parse_result(body_text: str) -> Dict[str, Any]:
    """Pull numeric fields out of the rendered page text.

    Returns a dict with every pattern that matched plus a `not_loaded_cards`
    list when the site reported card-lookup failures. ``commander_bracket`` is
    cast to int; everything else stays as the raw string the site rendered so
    upstream can decide how to coerce.
    """
    result: Dict[str, Any] = {}
    for key, pattern in RESULT_PATTERNS.items():
        match = pattern.search(body_text)
        if match:
            value = match.group(1)
            if key == "commander_bracket":
                try:
                    result[key] = int(value)
                except ValueError:
                    result[key] = value
            else:
                result[key] = value

    not_loaded: List[str] = []
    not_loaded_match = _NOT_LOADED_HEADER.search(body_text)
    if not_loaded_match:
        block = not_loaded_match.group(1)
        for line_match in _NOT_LOADED_LINE.finditer(block):
            not_loaded.append(line_match.group(1).strip())
    if not_loaded:
        result["not_loaded_cards"] = not_loaded
    return result


class EDHPowerLevelClient(AbstractContextManager):
    """Context manager that drives the EDHPowerLevel page per deck.

    Parameters:

    - ``headless`` — set False to watch the browser drive the page (debugging).
    - ``page_timeout_ms`` — Playwright per-action timeout (navigation, waits).
    - ``analysis_max_wait_sec`` — max wall-clock to poll for the bracket result
      to appear and stabilize. The poll exits earlier as soon as the result is
      stable; this is only the upper bound when the backend is slow.
    - ``analysis_stable_sec`` — how long the bracket must hold the same value
      before we accept it as final.
    - ``context_recycle_every`` — kept for back-compat but no longer
      load-bearing. Each ``analyze`` call now uses a fresh browser context to
      prevent stale-read bugs caused by reusing the same page between decks.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        page_timeout_ms: int = 60_000,
        analysis_wait_sec: float = 8.0,
        analysis_max_wait_sec: float = 45.0,
        analysis_stable_sec: float = 3.0,
        context_recycle_every: int = 50,
    ) -> None:
        self.headless = headless
        self.page_timeout_ms = page_timeout_ms
        # analysis_wait_sec is kept for back-compat; treated as a *minimum*
        # wait before we start polling for a stable result.
        self.analysis_min_wait_sec = max(float(analysis_wait_sec), 0.5)
        self.analysis_max_wait_sec = max(float(analysis_max_wait_sec), self.analysis_min_wait_sec + 1.0)
        self.analysis_stable_sec = max(float(analysis_stable_sec), 0.5)
        self.context_recycle_every = max(int(context_recycle_every), 1)

        self._playwright = None
        self._browser: Optional[Browser] = None

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self) -> "EDHPowerLevelClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # --------------------------------------------------------------------- API
    def analyze(self, decklist: str) -> Dict[str, Any]:
        """Submit ``decklist`` and return the parsed scoring fields.

        Uses a fresh browser context per call so a previous deck's rendered
        result can't be picked up by ``inner_text`` after a slow analysis.
        Polls for the bracket to appear and remain stable instead of sleeping
        for a fixed duration.

        On success returns ``{"commander_bracket": 4, "power_level": "8.40",
        ...}``. On failure returns ``{"error": "...", "error_type": "..."}``.
        """
        if not decklist.strip():
            return {"error": "empty_decklist", "error_type": "ValueError"}
        if self._browser is None:
            return {"error": "client_not_started", "error_type": "RuntimeError"}

        started_at = datetime.now(timezone.utc).isoformat()
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None
        try:
            context = self._browser.new_context()
            context.set_default_timeout(self.page_timeout_ms)
            page = context.new_page()
            page.goto(EDHPL_URL, wait_until="networkidle")

            # Capture the page's default scoring values BEFORE doing anything
            # else. The site renders a static "preview" (bracket=4, pl=5.55,
            # score=447, impact=516.00, efficiency=4.82, playability=51.8) when
            # no decklist has been analyzed yet. If the in-browser scoring is
            # slow, our polling can lock onto that default state and return
            # wrong labels. We snapshot the default before filling/clicking so
            # the polling can reject any reading that matches.
            default_body = page.inner_text("body")
            default_parsed = _parse_result(default_body)
            default_fingerprint = _fingerprint(default_parsed)

            textarea = page.wait_for_selector("textarea#decklist", timeout=self.page_timeout_ms)
            textarea.fill(decklist)

            analyze = page.wait_for_selector(
                "button:has-text('Analyze')", timeout=self.page_timeout_ms
            )
            analyze.click()

            parsed, body_text = self._wait_for_stable_result(page, default_fingerprint)

            if "commander_bracket" not in parsed:
                snippet = body_text[:600].replace("\n", " ")
                return {
                    "error": "no_bracket_in_result",
                    "error_type": "ParseError",
                    "page_snippet": snippet,
                    "started_at": started_at,
                }

            # Defensive: if the polling returned a reading that exactly matches
            # the pre-Analyze default state, something is wrong upstream.
            if _fingerprint(parsed) == default_fingerprint:
                return {
                    "error": "stuck_on_initial_page_state",
                    "error_type": "StaleReadError",
                    "default_fingerprint": list(default_fingerprint),
                    "started_at": started_at,
                }

            parsed["started_at"] = started_at
            parsed["finished_at"] = datetime.now(timezone.utc).isoformat()
            return parsed
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            return {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "started_at": started_at,
            }
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------- poll
    def _wait_for_stable_result(
        self,
        page: "Page",
        default_fingerprint: tuple,
    ) -> tuple[Dict[str, Any], str]:
        """Poll the DOM until the bracket appears and stays the same.

        The site renders the bracket after the in-browser scoring runs; the
        Cloud Run card-data backend can be slow under load, so a fixed wait
        risks reading a stale (empty or previous) page. We instead poll
        every 250ms, require the bracket value to repeat across consecutive
        reads spanning ``analysis_stable_sec`` seconds, and bail out at
        ``analysis_max_wait_sec``.

        ``default_fingerprint`` is ``(power_level, score, impact)`` captured
        from the page before Analyze was clicked. Any polling read whose
        triple matches this fingerprint is treated as "not yet calculated"
        — the streak is reset and we keep waiting.
        """
        time.sleep(self.analysis_min_wait_sec)
        deadline = time.monotonic() + (self.analysis_max_wait_sec - self.analysis_min_wait_sec)
        poll_interval = 0.25
        stable_needed = max(int(self.analysis_stable_sec / poll_interval), 2)
        last_bracket: Optional[int] = None
        stable_streak = 0
        last_body = ""
        last_parsed: Dict[str, Any] = {}
        saw_non_default = False
        while True:
            body_text = page.inner_text("body")
            parsed = _parse_result(body_text)
            current = parsed.get("commander_bracket")
            current_fp = _fingerprint(parsed)
            is_default_state = current_fp == default_fingerprint
            if current is not None and isinstance(current, int) and not is_default_state:
                saw_non_default = True
                if current == last_bracket:
                    stable_streak += 1
                else:
                    last_bracket = current
                    stable_streak = 1
                if stable_streak >= stable_needed:
                    return parsed, body_text
            else:
                # Still showing default state OR bracket unparseable — reset
                # the streak; we must not accept a default-state reading even
                # if it happens to be stable.
                stable_streak = 0
                last_bracket = None
            # Only retain the last NON-default body/parsed as fallback. If we
            # only ever saw default values, return an empty parsed so the
            # caller raises ``no_bracket_in_result`` instead of returning
            # bogus default labels.
            if not is_default_state:
                last_body = body_text
                last_parsed = parsed
            if time.monotonic() >= deadline:
                if saw_non_default:
                    return last_parsed, last_body
                # Calculator never produced real numbers within the deadline.
                return {}, body_text
            time.sleep(poll_interval)


__all__ = ["EDHPowerLevelClient", "decklist_text", "_parse_result", "_fingerprint"]
