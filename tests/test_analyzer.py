"""
Tests for HitDataParser and ReportWriter.

Run: pytest tests/ -v
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from search_keyword_performance import HitDataParser, ReportWriter

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "data.sql")


#search engine parsing

def test_google_extracts_domain_and_keyword():
    domain, kw = HitDataParser.get_search_info(
        "http://www.google.com/search?hl=en&q=Ipod&client=firefox"
    )
    assert domain == "google.com"
    assert kw == "Ipod"


def test_yahoo_uses_p_param_and_decodes_spaces():
    domain, kw = HitDataParser.get_search_info(
        "http://search.yahoo.com/search?p=cd+player&ei=UTF-8"
    )
    assert domain == "search.yahoo.com"
    assert kw == "cd player"   # parse_qs decodes + as space


def test_internal_referrer_returns_none():
    assert HitDataParser.get_search_info("http://www.esshopzilla.com/cart/") == (None, None)
    assert HitDataParser.get_search_info("") == (None, None)


#revenue extraction 

def test_revenue_single_product():
    assert HitDataParser.get_revenue("Electronics;Zune - 32GB;1;250;") == 250.0


def test_revenue_multi_product_summed():
    # two products in one hit — should sum
    assert HitDataParser.get_revenue("Electronics;A;1;100;,Clothing;B;2;50;") == 150.0


def test_revenue_empty_returns_zero():
    assert HitDataParser.get_revenue("") == 0.0
    assert HitDataParser.get_revenue("Electronics;A;1;;") == 0.0


#purchase event detection (critical edge cases)

def test_purchase_detected():
    assert HitDataParser.is_purchase("1") is True
    assert HitDataParser.is_purchase("1,12,200") is True


def test_cart_events_are_not_purchases():
    # "1" in "10" is True in Python string search — that's the bug this prevents
    assert HitDataParser.is_purchase("10") is False
    assert HitDataParser.is_purchase("11") is False
    assert HitDataParser.is_purchase("12") is False
    assert HitDataParser.is_purchase("") is False


#full pipeline + output 

def test_pipeline_results_and_sort():
    if not os.path.exists(DATA):
        pytest.skip("data/data.sql not found")

    results = HitDataParser(DATA).process()

    assert len(results) == 3

    # top result
    assert results[0] == ("google.com", "Ipod", 290.0)

    # sorted descending
    revenues = [r[2] for r in results]
    assert revenues == sorted(revenues, reverse=True)


def test_report_writer_filename_and_content():
    from datetime import datetime
    w = ReportWriter(run_date=datetime(2009, 9, 27))
    assert w.filename() == "2009-09-27_SearchKeywordPerformance.tab"

    with tempfile.TemporaryDirectory() as tmp:
        path = w.write([("google.com", "Ipod", 290.0)], output_dir=tmp)
        lines = open(path).readlines()

    assert lines[0].strip().split("\t") == ["Search Engine Domain", "Search Keyword", "Revenue"]
    assert "290.00" in lines[1]