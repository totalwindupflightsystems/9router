"""MON-DOGFOOD-039 regression tests.

Covers:
- exporter: additive _total aliases (acceptance query convention) — RED-proven by
  reverting exporter.py (pre-fix the alias series are absent).
- exporter_wrapper2: 14-day window still holds with the standalone repo path.
"""
import importlib.util
import os
import re
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


exporter = load_module("cost_exporter_039", "exporter.py")


def seed_db(tmp, ages_days=(74,)):
    """Seed a state.db with one usage row per age (days before today)."""
    db = Path(tmp) / "state.db"
    conn = sqlite3.connect(db)
    conn.executescript("""CREATE TABLE sessions(id TEXT,started_at REAL,cwd TEXT,title TEXT);
    CREATE TABLE session_model_usage(session_id TEXT,billing_base_url TEXT,input_tokens INTEGER,
    output_tokens INTEGER,cache_read_tokens INTEGER,cache_write_tokens INTEGER,
    estimated_cost_usd REAL,api_call_count INTEGER);""")
    for i, age in enumerate(ages_days):
        started = date.today() - timedelta(days=age)
        ts = started.strftime("%s")
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?)", (f"s{i}", ts, None, "Review example tick #4"))
        conn.execute(
            "INSERT INTO session_model_usage VALUES(?,?,?,?,?,?,?,?)",
            (f"s{i}", "https://api.example/v1", 100, 20, 300, 8, 0.25, 5),
        )
    conn.commit()
    conn.close()
    return db


class AliasTests(unittest.TestCase):
    def test_total_aliases_match_base_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = seed_db(tmp)
            text = exporter.scrape_text(db)
            day = (date.today() - timedelta(days=74)).isoformat()
            label = f'day="{day}",lane="example",provider="https://api.example/v1"'
            self.assertIn(f"hermes_session_tokens_in{{{label}}} 100", text)
            self.assertIn(f"hermes_session_tokens_in_total{{{label}}} 100", text)
            self.assertIn(f"hermes_session_tokens_out{{{label}}} 20", text)
            self.assertIn(f"hermes_session_tokens_out_total{{{label}}} 20", text)
            self.assertIn("# TYPE hermes_session_tokens_in_total gauge", text)
            self.assertIn("# TYPE hermes_session_tokens_out_total gauge", text)

    def test_alias_series_count_matches_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = seed_db(tmp)
            text = exporter.scrape_text(db)
            self.assertEqual(
                len(re.findall(r"^hermes_session_tokens_in\{", text, re.M)),
                len(re.findall(r"^hermes_session_tokens_in_total\{", text, re.M)),
            )
            self.assertEqual(
                len(re.findall(r"^hermes_session_tokens_out\{", text, re.M)),
                len(re.findall(r"^hermes_session_tokens_out_total\{", text, re.M)),
            )
            self.assertGreater(len(re.findall(r"^hermes_session_tokens_in\{", text, re.M)), 0)


class WrapperWindowTests(unittest.TestCase):
    def test_wrapper_window_keeps_recent_and_drops_old(self):
        wrapper = load_module("cost_exporter_wrapper_039", "exporter_wrapper2.py")
        with tempfile.TemporaryDirectory() as tmp:
            db = seed_db(tmp, ages_days=(30, 1))  # old row dropped, recent row kept
            text = wrapper.scrape_text_bounded(db)
            old_day = (date.today() - timedelta(days=30)).isoformat()
            recent_day = (date.today() - timedelta(days=1)).isoformat()
            self.assertNotIn(f'day="{old_day}"', text)
            self.assertIn(f'day="{recent_day}"', text)
            self.assertIn("# HELP hermes_session_tokens_in", text)
            self.assertIn("# TYPE hermes_session_tokens_in_total gauge", text)

    def test_wrapper_all_days_env_bypasses_window(self):
        old = os.environ.pop("HERMES_EXPORT_ALL_DAYS", None)
        os.environ["HERMES_EXPORT_ALL_DAYS"] = "1"
        try:
            wrapper = load_module("cost_exporter_wrapper_all_039", "exporter_wrapper2.py")
            with tempfile.TemporaryDirectory() as tmp:
                db = seed_db(tmp, ages_days=(30,))
                text = wrapper.scrape_text_bounded(db)
                self.assertIn("hermes_session_tokens_in{", text)
        finally:
            os.environ.pop("HERMES_EXPORT_ALL_DAYS", None)
            if old is not None:
                os.environ["HERMES_EXPORT_ALL_DAYS"] = old


if __name__ == "__main__":
    unittest.main()
