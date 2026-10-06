import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cost_exporter", Path(__file__).with_name("exporter.py"))
exporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(exporter)


class ExporterTests(unittest.TestCase):
    def test_lane_inference(self):
        self.assertEqual(exporter.lane_for(None, "Review sync-worker tick #8"), "sync-worker")
        self.assertEqual(exporter.lane_for("/work/monitoring-MON-GAP-012", "Other"), "MON-GAP-012")
        self.assertEqual(exporter.lane_for(None, None), "unattributed")

    def test_daily_metrics_and_billing_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            conn = sqlite3.connect(db)
            conn.executescript("""CREATE TABLE sessions(id TEXT,started_at REAL,cwd TEXT,title TEXT);
            CREATE TABLE session_model_usage(session_id TEXT,billing_base_url TEXT,input_tokens INTEGER,
            output_tokens INTEGER,cache_read_tokens INTEGER,cache_write_tokens INTEGER,
            estimated_cost_usd REAL,api_call_count INTEGER);
            INSERT INTO sessions VALUES('s',1791244800,NULL,'Review example-sync tick #4');
            INSERT INTO session_model_usage VALUES('s','https://api.example/v1',100,20,300,8,.25,5);""")
            conn.commit(); conn.close()
            text = exporter.scrape_text(db)
            label = 'day="2026-10-06",lane="example-sync",provider="https://api.example/v1"'
            self.assertIn(f'hermes_session_tokens_in{{{label}}} 100', text)
            self.assertIn(f'hermes_session_est_cost_usd{{{label}}} 0.25', text)
            self.assertIn(f'hermes_session_cache_hit_ratio{{{label}}} 0.75', text)
            self.assertIn(f'hermes_session_cost_per_api_call_usd{{{label}}} 0.05', text)

    def test_missing_db_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            exporter.scrape_text(Path("/missing/state.db"))


if __name__ == "__main__":
    unittest.main()
