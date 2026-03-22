#!/usr/bin/env python3
"""
Search Keyword Performance
Answers: which search engines + keywords drive the most revenue?

Usage: python search_keyword_performance.py data/data.sql
"""

import csv
import sys
import os
import logging
from datetime import datetime, timezone
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Tuple, List


# search engine domain -> query param that holds the keyword
SE_DOMAINS: Dict[str, str] = {
    "google.com"       : "q",
    "bing.com"         : "q",
    "msn.com"          : "q",
    "search.yahoo.com" : "p",
    "ask.com"          : "q",
}

PURCHASE_EVENT = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class HitDataParser:
    """
    Two-pass attribution over hit-level TSV data.
    Pass 1 maps each IP to its first search-engine referrer.
    Pass 2 accumulates revenue for purchase hits against that map.
    """

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.session_map: Dict[str, Tuple[str, str]] = {}       # ip -> (domain, keyword)
        self.rev_totals: Dict[Tuple[str, str], float] = defaultdict(float)

    @staticmethod
    def get_search_info(referrer: str) -> Tuple[Optional[str], Optional[str]]:
        """Pull (domain, keyword) from a referrer URL. None, None if not a search engine."""
        if not referrer or not referrer.strip():
            return None, None
        try:
            parsed = urlparse(referrer)
            host = parsed.netloc.lower()
            # strip www. so www.google.com matches our dict key
            host_clean = host[4:] if host.startswith("www.") else host

            for domain, kw_param in SE_DOMAINS.items():
                if host_clean == domain or host == domain:
                    kws = parse_qs(parsed.query).get(kw_param, [])
                    if kws:
                        return domain, kws[0]
        except Exception:
            pass
        return None, None

    @staticmethod
    def get_revenue(product_list: str) -> float:
        """
        Revenue is at semicolon index [3] of each comma-delimited product.
        Format: Category;Name;Qty;Revenue;...
        """
        if not product_list or not product_list.strip():
            return 0.0

        total = 0.0
        for item in product_list.split(","):
            parts = item.split(";")
            if len(parts) >= 4 and parts[3].strip():
                try:
                    total += float(parts[3].strip())
                except ValueError:
                    pass
        return total

    @staticmethod
    def is_purchase(event_list: str) -> bool:
        # split on comma before checking — "1" in "10" is True in Python, which is wrong
        # print(f"DEBUG event_list={event_list!r}")
        if not event_list:
            return False
        return PURCHASE_EVENT in [e.strip() for e in event_list.split(",")]

    def _map_sessions(self, rows: List[Dict]) -> None:
        """Pass 1 — first search-engine referrer per IP wins."""
        for row in rows:
            ip = row.get("ip", "").strip()
            if not ip or ip in self.session_map:
                continue
            domain, kw = self.get_search_info(row.get("referrer", ""))
            if domain and kw:
                self.session_map[ip] = (domain, kw)
                log.info("session  %-16s  ->  %s / %r", ip, domain, kw)

    def _sum_revenue(self, rows: List[Dict]) -> None:
        """Pass 2 — attribute purchase revenue back to the session's search engine."""
        for row in rows:
            if not self.is_purchase(row.get("event_list", "")):
                continue

            ip  = row.get("ip", "").strip()
            rev = self.get_revenue(row.get("product_list", ""))

            if rev <= 0 or ip not in self.session_map:
                continue

            domain, kw = self.session_map[ip]
            self.rev_totals[(domain, kw)] += rev
            log.info("attributed  $%.2f  ->  %s / %r", rev, domain, kw)

    def process(self) -> List[Tuple[str, str, float]]:
        log.info("Reading %s", self.filepath)
        try:
            with open(self.filepath, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh, delimiter="\t"))
        except FileNotFoundError:
            log.error("File not found: %s", self.filepath)
            sys.exit(1)

        log.info("Loaded %d rows", len(rows))

        self._map_sessions(rows)
        self._sum_revenue(rows)

        results = [
            (domain, kw, rev)
            for (domain, kw), rev in self.rev_totals.items()
        ]
        results.sort(key=lambda x: x[2], reverse=True)
        return results


class ReportWriter:
    """Tab-delimited output file, named by data date."""

    HEADERS = ["Search Engine Domain", "Search Keyword", "Revenue"]

    def __init__(self, run_date: Optional[datetime] = None) -> None:
        self.run_date = run_date or datetime.now(timezone.utc)

    def filename(self) -> str:
        return self.run_date.strftime("%Y-%m-%d") + "_SearchKeywordPerformance.tab"

    def write(self, results: List[Tuple[str, str, float]], output_dir: str = ".") -> str:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, self.filename())

        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(self.HEADERS)
            for domain, kw, rev in results:
                w.writerow([domain, kw, f"{rev:.2f}"])

        log.info("Written: %s", out_path)
        return out_path


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {os.path.basename(__file__)} <data_file>")
        sys.exit(1)

    parser  = HitDataParser(sys.argv[1])
    results = parser.process()

    writer   = ReportWriter()
    out_path = writer.write(results)

    print()
    print(f"  {'Search Engine':<22} {'Keyword':<22} {'Revenue':>10}")
    print("  " + "-" * 58)
    for d, k, r in results:
        print(f"  {d:<22} {k:<22} ${r:>9.2f}")
    print(f"\n  Output -> {out_path}\n")


if __name__ == "__main__":
    main()