import unittest
import xml.etree.ElementTree as ET

from omnisource.domain import App, Catalog
from omnisource.feeds.calendar import render_calendar, render_filtered_rss


class CalendarTests(unittest.TestCase):
    def test_calendar_folds_utf8_and_excludes_unknown_dates(self):
        app = App(
            slug="demo",
            raw={"slug": "demo", "name": "Demo", "bundleIdentifier": "com.test.demo", "developerName": "Tester"},
        )
        catalog = Catalog(source={"baseURL": "https://example.com"}, clients=[], apps=[app])
        state = {
            "demo": {
                "versions": [
                    {
                        "version": "1.0",
                        "date": "2026-10-01",
                        "downloadURL": "https://example.com/a.ipa",
                        "localizedDescription": "héllo, world; " * 30,
                    }
                ]
            }
        }
        cal = render_calendar(catalog, state)
        self.assertIn("DTSTART;VALUE=DATE:20261001", cal)
        self.assertIn("DTEND;VALUE=DATE:20261002", cal)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in cal.split("\r\n")))
        rss = render_filtered_rss(catalog, state, slugs={"demo"}, title="Demo", path="test.xml")
        self.assertEqual(ET.fromstring(rss).findtext("./channel/item/title"), "Demo v1.0")  # noqa: S314 - local fixture
        state["demo"]["versions"][0]["date"] = ""
        self.assertNotIn("BEGIN:VEVENT", render_calendar(catalog, state))


if __name__ == "__main__":
    unittest.main()
