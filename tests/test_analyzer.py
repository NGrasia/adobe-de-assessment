"""
Unit tests for HitDataParser and ReportWriter.

Run:
    pytest tests/test_analyzer.py -v
    pytest tests/test_analyzer.py -v --cov=src --cov-report=term-missing
"""

import os
import sys
import tempfile
import pytest

# Make sure pytest can find the src/ folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from search_keyword_performance import HitDataParser, ReportWriter


# ---------------------------------------------------------------------------
# extract_search_info
# ---------------------------------------------------------------------------

class TestExtractSearchInfo:

    def test_google_returns_domain_and_keyword(self):
        url = "http://www.google.com/search?hl=en&q=Ipod&client=firefox"
        domain, kw = HitDataParser.extract_search_info(url)
        assert domain == "google.com"
        assert kw     == "Ipod"

    def test_bing_returns_correctly(self):
        url = "http://www.bing.com/search?q=Zune&form=QBLH"
        domain, kw = HitDataParser.extract_search_info(url)
        assert domain == "bing.com"
        assert kw     == "Zune"

    def test_yahoo_uses_p_param(self):
        url = "http://search.yahoo.com/search?p=cd+player&ei=UTF-8"
        domain, kw = HitDataParser.extract_search_info(url)
        assert domain == "yahoo.com"
        assert kw     == "cd player"

    def test_internal_referrer_returns_none(self):
        url = "http://www.esshopzilla.com/cart/"
        assert HitDataParser.extract_search_info(url) == (None, None)

    def test_empty_string_returns_none(self):
        assert HitDataParser.extract_search_info("")    == (None, None)
        assert HitDataParser.extract_search_info("  ") == (None, None)

    def test_none_returns_none(self):
        assert HitDataParser.extract_search_info(None) == (None, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_revenue
# ---------------------------------------------------------------------------

class TestParseRevenue:

    def test_single_product_with_revenue(self):
        assert HitDataParser.parse_revenue("Electronics;Zune - 32GB;1;250;") == 250.0

    def test_multiple_products_summed(self):
        pl = "Electronics;Item A;1;100;,Clothing;Item B;2;50;"
        assert HitDataParser.parse_revenue(pl) == 150.0

    def test_empty_revenue_field_returns_zero(self):
        assert HitDataParser.parse_revenue("Electronics;Item;1;;") == 0.0

    def test_empty_product_list_returns_zero(self):
        assert HitDataParser.parse_revenue("") == 0.0

    def test_none_returns_zero(self):
        assert HitDataParser.parse_revenue(None) == 0.0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_purchase  — the critical edge-case tests
# ---------------------------------------------------------------------------

class TestIsPurchase:

    def test_purchase_event_alone(self):
        assert HitDataParser.is_purchase("1") is True

    def test_purchase_among_other_events(self):
        assert HitDataParser.is_purchase("1,12,200") is True

    # "1" in "10" is True in Python string search — split+exact-match prevents this
    def test_event_10_is_NOT_a_purchase(self):
        assert HitDataParser.is_purchase("10") is False

    def test_event_11_is_NOT_a_purchase(self):
        assert HitDataParser.is_purchase("11") is False

    def test_event_12_is_NOT_a_purchase(self):
        assert HitDataParser.is_purchase("12") is False

    def test_empty_returns_false(self):
        assert HitDataParser.is_purchase("")   is False
        assert HitDataParser.is_purchase(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Full pipeline integration test — requires data/data.tab
# ---------------------------------------------------------------------------

class TestFullPipeline:

    SAMPLE_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "data.tab")

    def test_process_returns_three_results(self):
        if not os.path.exists(self.SAMPLE_DATA):
            pytest.skip("data/data.tab not found")
        results = HitDataParser(self.SAMPLE_DATA).process()
        assert len(results) == 3

    def test_first_result_is_google_ipod_290(self):
        if not os.path.exists(self.SAMPLE_DATA):
            pytest.skip("data/data.tab not found")
        results = HitDataParser(self.SAMPLE_DATA).process()
        domain, keyword, revenue = results[0]
        assert domain  == "google.com"
        assert keyword == "Ipod"
        assert revenue == 290.0

    def test_second_result_is_bing_zune_250(self):
        if not os.path.exists(self.SAMPLE_DATA):
            pytest.skip("data/data.tab not found")
        results = HitDataParser(self.SAMPLE_DATA).process()
        assert results[1][0] == "bing.com"
        assert results[1][2] == 250.0

    def test_results_sorted_descending(self):
        if not os.path.exists(self.SAMPLE_DATA):
            pytest.skip("data/data.tab not found")
        results = HitDataParser(self.SAMPLE_DATA).process()
        revenues = [r[2] for r in results]
        assert revenues == sorted(revenues, reverse=True)


# ---------------------------------------------------------------------------
# ReportWriter
# ---------------------------------------------------------------------------

class TestReportWriter:

    def test_filename_format(self):
        from datetime import datetime
        w = ReportWriter(run_date=datetime(2009, 9, 27))
        assert w.filename() == "2009-09-27_SearchKeywordPerformance.tab"

    def test_write_creates_file_with_correct_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            w    = ReportWriter()
            path = w.write([("google.com", "Ipod", 290.0)], output_dir=tmp)
            assert os.path.exists(path)
            with open(path) as fh:
                lines = fh.readlines()
            header = lines[0].strip().split("\t")
            assert header == ["Search Engine Domain", "Search Keyword", "Revenue"]

    def test_write_revenue_formatted_to_2dp(self):
        with tempfile.TemporaryDirectory() as tmp:
            w    = ReportWriter()
            path = w.write([("google.com", "Ipod", 290.0)], output_dir=tmp)
            with open(path) as fh:
                data_line = fh.readlines()[1]
            assert "290.00" in data_line