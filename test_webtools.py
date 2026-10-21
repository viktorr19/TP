"""Verificari locale pentru raport, fara conexiuni la internet."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from web_lab import main, webtools


class ReportTests(unittest.TestCase):
    """Verifica parsarea, raportul si erorile de retea."""

    def test_html_and_links(self):
        """Verifica entitati, ghilimele simple si URL-uri relative."""
        html = "<TITLE>Test &amp; titlu</TITLE><a href='next'>A</a><a HREF='/x'>B</a>"
        self.assertEqual(webtools.get_title(html), "Test & titlu")
        self.assertEqual(webtools.get_title("<p>Fara titlu</p>"), "")
        internal, external = webtools.split_links(
            webtools.extract_links(html) + ["mailto:a@example.com", "https://other.org/"],
            "https://example.com/folder/page",
        )
        self.assertEqual(internal, ["https://example.com/folder/next", "https://example.com/x"])
        self.assertEqual(external, ["https://other.org/"])
        self.assertEqual(webtools.disallowed_paths(
            "Disallow: /admin # comentariu\ndisallow: /private\nDisallow:"
        ), ["/admin", "/private"])

    def test_report_survives_optional_failures(self):
        """O eroare TLS nu impiedica salvarea celorlalte date."""
        response = requests.Response()
        response.status_code = 200
        response.url = "https://example.com/"
        response._content = b"<title>Test</title><a href='/about'>About</a>"
        redirect = requests.Response()
        redirect.status_code = 301
        redirect.url = "http://example.com"
        redirect.headers["Location"] = response.url
        response.history = [redirect]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            with patch.object(webtools, "OUTPUT_DIR", Path(directory)), \
                 patch.object(webtools, "fetch", return_value=response), \
                 patch.object(webtools, "resolve", return_value="192.0.2.1"), \
                 patch.object(webtools, "cert_days_left", side_effect=OSError("TLS indisponibil")), \
                 patch.object(webtools, "fetch_robots", return_value="Disallow: /admin"), \
                 patch.object(webtools.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
                report = webtools.site_report("https://example.com")
            self.assertEqual(report["redirectionari"][0]["destinatie"], response.url)
            self.assertEqual(report["linkuri_interne"], 1)
            self.assertIsNone(report["certificat_zile"])
            self.assertIn("certificat", report["erori"])
            self.assertEqual(json.loads((Path(directory) / "report.json").read_text(encoding="utf-8")), report)

    def test_cli_errors(self):
        """URL-urile invalide si erorile HTTP produc un cod de iesire util."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main.main(["invalid"]), 1)
            with patch.object(webtools, "fetch", side_effect=requests.Timeout("timeout")):
                self.assertEqual(main.main(["https://example.com"]), 1)


if __name__ == "__main__":
    unittest.main()

