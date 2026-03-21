#!/usr/bin/env python3
"""
Search Keyword Performance Analyzer

Question: How much revenue comes from external search engines,
and which keywords perform best?

Usage:
    python search_keyword_performance.py data/data.tab

Output:
    YYYY-mm-dd_SearchKeywordPerformance.tab  (tab-delimited, sorted by revenue DESC)
"""

import csv
import sys
import os
import logging
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Tuple, List


# ---------------------------------------------------------------------------
# CONFIG — all tuneable values in one place.
# Adding a new search engine = one dict entry, no logic change needed.
# ---------------------------------------------------------------------------

SEARCH_ENGINES: Dict[str, str] = {
    "google.com"       : "q",
    "bing.com"         : "q",
    "msn.com"          : "q",   # legacy MSN search
    "yahoo.com"        : "p",   # yahoo uses "p" not "q"
    "search.yahoo.com" : "p",
    "ask.com"          : "q",
}

PURCHASE_EVENT = "1"   # Adobe Analytics purchase event code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ===========================================================================
class HitDataParser:
    """
    Reads Adobe Analytics hit-level TSV data and builds a revenue attribution
    report: which search engine + keyword initiated each purchasing session.

    Session model  : IP address is the session key.
    Attribution    : first-touch — the first search referrer for an IP wins.
    Processing     : two-pass over the same row list.
                     Pass 1 builds the session -> search mapping.
                     Pass 2 accumulates revenue for purchase hits.
    """

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        # ip -> (search_engine_domain, keyword)
        self.session_search: Dict[str, Tuple[str, str]] = {}
        # (domain, keyword) -> cumulative revenue
        self.revenue_map: Dict[Tuple[str, str], float] = defaultdict(float)

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def extract_search_info(referrer: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (domain, keyword) if referrer is a known search engine, else (None, None)."""
        if not referrer or not referrer.strip():
            return None, None
        try:
            parsed = urlparse(referrer)
            host = parsed.netloc.lower()
            # Strip "www." so "www.google.com" matches key "google.com"
            canonical = host[4:] if host.startswith("www.") else host
            for se_domain, kw_param in SEARCH_ENGINES.items():
                if canonical == se_domain or host == se_domain:
                    kws = parse_qs(parsed.query).get(kw_param, [])
                    if kws:
                        return se_domain, kws[0]
        except Exception as exc:
            log.debug("Skipping unparseable referrer %r: %s", referrer, exc)
        return None, None

    @staticmethod
    def parse_revenue(product_list: str) -> float:
        """
        Extract total revenue from product_list.
        Format (Appendix B): Category;Name;Qty;Revenue;CustomEvent,...
        Revenue sits at semicolon-index 3 (0-based) of each comma-split product.
        """
        if not product_list or not product_list.strip():
            return 0.0
        total = 0.0
        for product in product_list.split(","):
            parts = product.split(";")
            if len(parts) >= 4 and parts[3].strip():
                try:
                    total += float(parts[3].strip())
                except ValueError:
                    log.debug("Non-numeric revenue field: %r", parts[3])
        return total

    @staticmethod
    def is_purchase(event_list: str) -> bool:
        """
        True when event_list contains the purchase code "1".
        Uses split + exact-match to avoid "1" matching "10" or "11".
        """
        if not event_list:
            return False
        return PURCHASE_EVENT in [e.strip() for e in event_list.split(",")]

    # ── core logic ──────────────────────────────────────────────────────────

    def _build_session_map(self, rows: List[Dict]) -> None:
        """Pass 1: record first search-engine referrer per IP."""
        for row in rows:
            ip = row.get("ip", "").strip()
            if not ip or ip in self.session_search:
                continue  # already mapped — first referrer wins
            domain, keyword = self.extract_search_info(row.get("referrer", ""))
            if domain and keyword:
                self.session_search[ip] = (domain, keyword)
                log.info("session  %-16s  ->  %s / %r", ip, domain, keyword)

    def _accumulate_revenue(self, rows: List[Dict]) -> None:
        """Pass 2: for purchase hits, add revenue to the attributed SE + keyword."""
        for row in rows:
            if not self.is_purchase(row.get("event_list", "")):
                continue
            ip = row.get("ip", "").strip()
            revenue = self.parse_revenue(row.get("product_list", ""))
            if revenue <= 0 or ip not in self.session_search:
                continue
            domain, keyword = self.session_search[ip]
            self.revenue_map[(domain, keyword)] += revenue
            log.info("attributed  $%.2f  ->  %s / %r", revenue, domain, keyword)

    def process(self) -> List[Tuple[str, str, float]]:
        """Read the file, run both passes, return results sorted by revenue DESC."""
        log.info("Reading %s", self.filepath)
        try:
            with open(self.filepath, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh, delimiter="\t"))
        except FileNotFoundError:
            log.error("File not found: %s", self.filepath)
            sys.exit(1)

        log.info("Loaded %d rows", len(rows))
        self._build_session_map(rows)
        self._accumulate_revenue(rows)

        results = [
            (domain, keyword, rev)
            for (domain, keyword), rev in self.revenue_map.items()
        ]
        results.sort(key=lambda item: item[2], reverse=True)
        return results


# ===========================================================================
class ReportWriter:
    """Writes results to a tab-delimited file per the assessment spec."""

    HEADERS = ["Search Engine Domain", "Search Keyword", "Revenue"]

    def __init__(self, run_date: Optional[datetime] = None) -> None:
        self.run_date = run_date or datetime.utcnow()

    def filename(self) -> str:
        return self.run_date.strftime("%Y-%m-%d") + "_SearchKeywordPerformance.tab"

    def write(
        self,
        results: List[Tuple[str, str, float]],
        output_dir: str = ".",
    ) -> str:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, self.filename())
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(self.HEADERS)
            for domain, keyword, revenue in results:
                w.writerow([domain, keyword, f"{revenue:.2f}"])
        log.info("Written: %s", out_path)
        return out_path


# ===========================================================================
def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {os.path.basename(__file__)} <data_file>")
        sys.exit(1)

    parser  = HitDataParser(sys.argv[1])
    results = parser.process()

    writer   = ReportWriter()
    out_path = writer.write(results)

    # print summary to stdout
    print()
    print(f"  {'Search Engine':<22} {'Keyword':<22} {'Revenue':>10}")
    print("  " + "-" * 58)
    for d, k, r in results:
        print(f"  {d:<22} {k:<22} ${r:>9.2f}")
    print()
    print(f"  Output -> {out_path}")
    print()


if __name__ == "__main__":
    main()