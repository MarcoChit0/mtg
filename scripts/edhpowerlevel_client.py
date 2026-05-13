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
    """Context manager that opens a single Chromium context for reuse.

    Parameters mirror the few knobs you'd want to tune from the CLI:

    - ``headless`` — set False to watch the browser drive the page (debugging).
    - ``page_timeout_ms`` — Playwright per-action timeout (navigation, waits).
    - ``analysis_wait_sec`` — extra wall-clock wait after clicking Analyze, to
      let the in-browser scoring run.
    - ``context_recycle_every`` — recreate the page after this many analyses
      to bound memory growth; the Highcharts + card art on the result page
      accumulate over time.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        page_timeout_ms: int = 60_000,
        analysis_wait_sec: float = 6.0,
        context_recycle_every: int = 50,
    ) -> None:
        self.headless = headless
        self.page_timeout_ms = page_timeout_ms
        self.analysis_wait_sec = analysis_wait_sec
        self.context_recycle_every = max(int(context_recycle_every), 1)

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._analyses_on_page = 0

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self) -> "EDHPowerLevelClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._open_fresh_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        for attr in ("_page", "_context", "_browser"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _open_fresh_page(self) -> None:
        assert self._browser is not None
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = self._browser.new_context()
        self._context.set_default_timeout(self.page_timeout_ms)
        self._page = self._context.new_page()
        self._page.goto(EDHPL_URL, wait_until="networkidle")
        self._analyses_on_page = 0

    # --------------------------------------------------------------------- API
    def analyze(self, decklist: str) -> Dict[str, Any]:
        """Submit ``decklist`` and return the parsed scoring fields.

        On success returns a dict like
        ``{"commander_bracket": 4, "power_level": "8.40", ...}``. On failure
        returns ``{"error": "...", "error_type": "..."}`` and leaves the
        browser in a known-good state for the next call.
        """
        if not decklist.strip():
            return {"error": "empty_decklist", "error_type": "ValueError"}

        if self._page is None or self._analyses_on_page >= self.context_recycle_every:
            self._open_fresh_page()
        assert self._page is not None

        page = self._page
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            # The Reset button clears any previous result without a full page
            # reload, so subsequent analyses don't see stale numbers.
            if self._analyses_on_page > 0:
                reset = page.query_selector("button:has-text('Reset')")
                if reset:
                    reset.click()
                    time.sleep(0.3)

            textarea = page.wait_for_selector("textarea#decklist", timeout=self.page_timeout_ms)
            textarea.fill(decklist)

            analyze = page.wait_for_selector(
                "button:has-text('Analyze')", timeout=self.page_timeout_ms
            )
            analyze.click()
            # Scoring is local JS; a fixed sleep is good enough and avoids
            # racing with the chart-rendering pipeline that fires later.
            time.sleep(self.analysis_wait_sec)

            body_text = page.inner_text("body")
            parsed = _parse_result(body_text)
            self._analyses_on_page += 1

            if "commander_bracket" not in parsed:
                # The page rendered but didn't show a bracket — usually means
                # the deck was rejected (too few cards, no commander). Keep
                # the warning text so we can debug downstream.
                snippet = body_text[:600].replace("\n", " ")
                return {
                    "error": "no_bracket_in_result",
                    "error_type": "ParseError",
                    "page_snippet": snippet,
                    "started_at": started_at,
                }

            parsed["started_at"] = started_at
            parsed["finished_at"] = datetime.now(timezone.utc).isoformat()
            return parsed
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            # On any browser-level error, recycle the page so the next call
            # starts from a clean slate.
            try:
                self._open_fresh_page()
            except Exception:
                pass
            return {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "started_at": started_at,
            }


__all__ = ["EDHPowerLevelClient", "decklist_text", "_parse_result"]
