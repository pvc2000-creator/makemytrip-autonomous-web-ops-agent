"""Offline tests for backend/services/aviationstack.py (no real API calls)."""
import os
import tempfile
import unittest
from unittest import mock

from backend.services import aviationstack as av

FAKE_OK = {
    "pagination": {"limit": 5, "offset": 0, "count": 1, "total": 1},
    "data": [
        {
            "flight_date": "2026-10-08",
            "flight_status": "scheduled",
            "departure": {"airport": "Indira Gandhi International", "iata": "DEL",
                          "terminal": "3", "gate": "A7", "delay": 12,
                          "scheduled": "2026-10-08T10:00:00+00:00", "estimated": None},
            "arrival": {"airport": "Chhatrapati Shivaji", "iata": "BOM", "delay": None,
                        "scheduled": "2026-10-08T12:10:00+00:00"},
            "airline": {"name": "Air India", "iata": "AI"},
            "flight": {"number": "101", "iata": "AI101", "icao": "AIC101"},
        }
    ],
}


class AviationstackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {
            "AVIATIONSTACK_API_KEY": "SECRET123",
            "AVIATIONSTACK_CACHE_DIR": self.tmp.name,
            "AVIATIONSTACK_MONTHLY_LIMIT": "2",
        }
        self.patcher = mock.patch.dict(os.environ, env, clear=False)
        self.patcher.start()
        os.environ.pop("AVIATIONSTACK_ALLOW_HTTP", None)

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"AVIATIONSTACK_API_KEY": ""}):
            with self.assertRaises(av.MissingApiKey):
                av.get_flights(dep_iata="DEL")

    def test_normalises_records(self):
        with mock.patch.object(av, "_http_get", return_value=FAKE_OK):
            rows = av.get_flights(dep_iata="del", arr_iata="bom", limit=5)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["flight_iata"], "AI101")
        self.assertEqual(r["entity_key"], "AI101|2026-10-08")
        self.assertEqual(r["dep_delay_min"], 12)
        self.assertIsNone(r["arr_delay_min"])
        self.assertEqual(r["source"], "aviationstack")

    def test_cache_avoids_second_request_and_quota(self):
        fake = mock.Mock(return_value=FAKE_OK)
        with mock.patch.object(av, "_http_get", fake):
            av.get_flights(dep_iata="DEL")
            av.get_flights(dep_iata="DEL")
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(av.requests_used_this_month(), 1)

    def test_quota_guard(self):
        fake = mock.Mock(return_value=FAKE_OK)
        with mock.patch.object(av, "_http_get", fake):
            av.get_flights(dep_iata="DEL")
            av.get_flights(dep_iata="BOM")
            with self.assertRaises(av.QuotaExceeded):
                av.get_flights(dep_iata="BLR")
        self.assertEqual(fake.call_count, 2)

    def test_error_message_hides_key(self):
        bad = {"error": {"code": "invalid_access_key", "message": "key SECRET123 is wrong"}}
        with mock.patch.object(av, "_http_get", return_value=bad):
            with self.assertRaises(av.AviationstackError) as ctx:
                av.get_flights(dep_iata="DEL")
        self.assertNotIn("SECRET123", str(ctx.exception))

    def test_https_refused_without_opt_in(self):
        refused = {"error": {"code": 105, "message": "https not allowed"}}
        fake = mock.Mock(return_value=refused)
        with mock.patch.object(av, "_http_get", fake):
            with self.assertRaises(av.AviationstackError) as ctx:
                av.get_flights(dep_iata="DEL")
        self.assertIn("ALLOW_HTTP", str(ctx.exception))
        self.assertEqual(fake.call_count, 1)  # never fell back to http

    def test_http_fallback_when_opted_in(self):
        refused = {"error": {"code": 105, "message": "https not allowed"}}
        fake = mock.Mock(side_effect=[refused, FAKE_OK])
        with mock.patch.dict(os.environ, {"AVIATIONSTACK_ALLOW_HTTP": "true"}):
            with mock.patch.object(av, "_http_get", fake):
                rows = av.get_flights(dep_iata="DEL")
        self.assertEqual(len(rows), 1)
        self.assertTrue(fake.call_args_list[1].args[0].startswith("http://"))


if __name__ == "__main__":
    unittest.main()
