"""
Lightweight tests for the health sidecar — run with `python -m unittest`.

These tests exercise the *plain* check functions and the HTTP routing layer
without needing a real Postgres or filesystem. We monkeypatch the
sub-checks; that's intentional — wiring real DB into unit tests would
defeat the purpose of a fast smoke check.
"""
from __future__ import annotations

import json
import os
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

# Force a known port that is unlikely to clash on dev machines / CI runners.
os.environ.setdefault("HEALTH_PORT", "18801")
os.environ.setdefault("HEALTH_LOGS_DIR", "/tmp/skuld-health-test-logs")

from health import server as h  # noqa: E402


class CheckDiskTests(unittest.TestCase):
    def test_returns_three_tuple(self) -> None:
        ok, pct, detail = h.check_disk()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(pct, float)
        self.assertIsInstance(detail, str)

    def test_missing_path_is_failure(self) -> None:
        with mock.patch.object(h, "DISK_PATH", "/definitely/not/here"):
            ok, pct, detail = h.check_disk()
            self.assertFalse(ok)
            self.assertEqual(pct, 0.0)
            self.assertIn("path-missing", detail)


class CheckCronTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path("/tmp/skuld-health-test-logs")
        self.tmpdir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for p in self.tmpdir.glob("*.log"):
            p.unlink(missing_ok=True)

    def test_no_files_is_failure(self) -> None:
        with mock.patch.object(h, "LOGS_DIR", self.tmpdir):
            ok, age, detail = h.check_cron()
            self.assertFalse(ok)
            self.assertIsNone(age)
            self.assertIn("no-log-files", detail)

    def test_recent_file_is_ok(self) -> None:
        f = self.tmpdir / "recent.log"
        f.write_text("hello")
        with mock.patch.object(h, "LOGS_DIR", self.tmpdir):
            ok, age, detail = h.check_cron()
            self.assertTrue(ok, detail)
            self.assertIsNotNone(age)
            self.assertLess(age, 5)

    def test_old_file_is_stale(self) -> None:
        f = self.tmpdir / "old.log"
        f.write_text("hello")
        # Pretend the file was last touched 30 hours ago.
        old = time.time() - (30 * 3600)
        os.utime(f, (old, old))
        with mock.patch.object(h, "LOGS_DIR", self.tmpdir):
            ok, age, _ = h.check_cron()
            self.assertFalse(ok)
            self.assertGreater(age, h.CRON_MAX_AGE_S)


class HttpRoutingTests(unittest.TestCase):
    """Bring up the real HTTP server on a port and probe it via urllib."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.port = int(os.environ["HEALTH_PORT"])
        cls.server = h._ThreadingHTTPServer(("127.0.0.1", cls.port), h._Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        # Tiny grace period so the listener is up before we probe it.
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_version(self) -> None:
        status, body = self._get("/version")
        self.assertEqual(status, 200)
        self.assertIn("version", body)

    def test_unknown_path_returns_404_json(self) -> None:
        status, body = self._get("/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not-found")

    def test_health_returns_503_when_db_down(self) -> None:
        # Force every check to a known state so the assertion is deterministic.
        with mock.patch.object(h, "check_db", return_value=(False, "fake")), \
                mock.patch.object(h, "check_disk", return_value=(True, 80.0, "ok")), \
                mock.patch.object(h, "check_cron", return_value=(True, 10, "ok")):
            status, body = self._get("/health")
            self.assertEqual(status, 503)
            self.assertFalse(body["ok"])
            self.assertFalse(body["db_ok"])

    def test_health_returns_200_when_all_ok(self) -> None:
        with mock.patch.object(h, "check_db", return_value=(True, "ok")), \
                mock.patch.object(h, "check_disk", return_value=(True, 80.0, "ok")), \
                mock.patch.object(h, "check_cron", return_value=(True, 10, "ok")):
            status, body = self._get("/health")
            self.assertEqual(status, 200)
            self.assertTrue(body["ok"])


if __name__ == "__main__":
    unittest.main()
