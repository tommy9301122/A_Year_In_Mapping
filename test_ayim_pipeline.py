"""Regression checks for the data-loss and classification bugs in the old notebook."""
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pandas as pd

from ayim_pipeline import (DIFFICULTY_COLUMNS, SET_COLUMNS, clean, fetch_period,
                           OsuClient, classify_hosts, mapper_is_new, validate)


def map_row(bid=1, sid=10, approved="2026-10-23 23:59:59", host="100", **extra):
    row = dict(beatmap_id=str(bid), beatmapset_id=str(sid), approved_date=approved,
               creator_id=host, mode="0", approved="1", genre_id="9", language_id="13",
               difficultyrating="2.7", title_unicode="", title="Title", artist_unicode=None,
               artist="Artist", version="Hard", favourite_count="4", playcount="50")
    return {**row, **extra}


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, path, params=None, **kwargs):
        self.calls.append((path, params))
        return next(self.pages)


class PipelineRegressionTests(unittest.TestCase):
    def test_inclusive_end_date_and_next_midnight_excluded(self):
        client = FakeClient([[map_row(), map_row(2, approved="2026-10-24 00:00:00")]])
        result = fetch_period(client, "2026-01-01", "2026-10-23")
        self.assertEqual(result.beatmap_id.tolist(), ["1"])

    def test_full_timestamp_pagination_overlaps_and_deduplicates(self):
        page = [map_row(i, approved="2026-01-01 00:00:00") for i in range(499)]
        last = map_row(499, approved="2026-01-02 12:34:56")
        client = FakeClient([page + [last], [last, map_row(500, approved="2026-01-03 00:00:00")]])
        result = fetch_period(client, "2026-01-01", "2026-01-31")
        self.assertEqual(len(result), 501)
        self.assertEqual(client.calls[1][1]["since"], "2026-01-02 12:34:55")

    def test_saturated_timestamp_fails_instead_of_losing_rows(self):
        page = [map_row(i, approved="2026-01-01 00:00:00") for i in range(500)]
        with self.assertRaisesRegex(RuntimeError, "saturated"):
            fetch_period(FakeClient([page]), "2026-01-01", "2026-01-31")

    def test_mapper_history_after_first_100_is_checked(self):
        page = [{"id": i, "ranked_date": "2026-06-01T00:00:00Z"} for i in range(100)]
        client = FakeClient([page, [{"id": 101, "ranked_date": "2025-12-31T23:59:59Z"}]])
        self.assertIs(mapper_is_new(client, "100", 2026), False)
        self.assertEqual(client.calls[1][1]["offset"], 100)

    def test_mapper_debut_year_and_no_ranked_history(self):
        self.assertIs(mapper_is_new(FakeClient([[{"id": 1, "ranked_date": "2026-01-01T00:00:00Z"}]]), "100", 2026), True)
        self.assertIs(mapper_is_new(FakeClient([[]]), "100", 2026), False)
        self.assertIs(mapper_is_new(FakeClient([[{"id": 1, "ranked_date": "2027-01-01T00:00:00Z"}]]), "100", 2026), False)

    def test_clean_labels_boundaries_and_host_without_owned_difficulty(self):
        rows = [map_row(i, difficultyrating=str(star), genre_id=str(genre), language_id=str(lang))
                for i, (star, genre, lang) in enumerate(zip([1.99, 2, 2.7, 4, 5.3, 6.5],
                                                            [9, 10, 11, 12, 13, 14], [7, 11, 13, 7, 11, 13]))]
        # Use separate sets because genre/language are set-level attributes.
        for row in rows:
            row["beatmapset_id"] = row["beatmap_id"]
        raw = pd.DataFrame(rows)
        owners = {str(i): "200" for i in range(6)}
        users = {"100": {"mapper": "Host", "country": "TW"}, "200": {"mapper": "Guest", "country": "JP"}}
        enriched, detail, sets = clean(raw, owners, users, {"100": True})
        self.assertTrue(enriched.genre_id.eq(raw.genre_id).all())
        self.assertTrue(enriched["mode"].eq("0").all())
        self.assertEqual(detail.difficulty_rating.tolist(), ["Easy", "Normal", "Hard", "Insane", "Expert", "Expert+"])
        self.assertEqual(detail.genre_id.tolist(), ["Hip Hop", "Electronic", "Metal", "Classical", "Folk", "Jazz"])
        self.assertEqual(detail.language_id.tolist(), ["French", "Italian", "Polish", "French", "Italian", "Polish"])
        self.assertTrue(detail.gd.eq(1).all())
        self.assertTrue(detail.mapper.eq("Guest").all())
        self.assertTrue(sets.mapper.eq("Host").all())
        self.assertTrue(detail.title_unicode.eq("Title").all())
        self.assertEqual(detail.columns.tolist(), DIFFICULTY_COLUMNS)
        self.assertEqual(sets.columns.tolist(), SET_COLUMNS)
        validate(detail, sets, "2026-01-01", "2026-10-23")

    def test_multiple_modes_reconcile_without_multiplying_difficulties(self):
        raw = pd.DataFrame([map_row(1), map_row(2), map_row(3, mode="3")])
        _, detail, sets = clean(raw, {"1": "100", "2": "100", "3": "100"}, {}, {"100": None})
        self.assertEqual(len(sets), 2)
        self.assertEqual(sets.beatmap_count.sum(), 3)
        self.assertTrue(sets.new_mapper.isna().all())
        validate(detail, sets, "2026-01-01", "2026-10-23")

    def test_history_prefilter_requires_ranked_evidence_and_checks_remaining(self):
        recent = pd.DataFrame([map_row(host="100"), {**map_row(2, host="200"), "approved": "4"}])
        older = pd.DataFrame([map_row(host="300")])
        with TemporaryDirectory() as folder, \
                patch("ayim_pipeline.fetch_period", side_effect=[recent, older]), \
                patch("ayim_pipeline.mapper_is_new", return_value=True) as history:
            result = classify_hosts(None, ["100", "200", "300"], 2026, Path(folder))
        self.assertEqual(result, {"100": False, "300": False, "200": True})
        history.assert_called_once_with(None, "200", 2026)

    def test_user_quota_pacing_and_429_wait(self):
        responses = [SimpleNamespace(status_code=429, headers={}),
                     SimpleNamespace(status_code=200, ok=True, json=lambda: {"users": []})]
        with TemporaryDirectory() as folder:
            client = OsuClient({}, cache_path=Path(folder) / "test.sqlite3")
            try:
                with patch.object(client.session, "request", side_effect=responses), \
                        patch("ayim_pipeline.time.sleep") as sleep, \
                        patch("ayim_pipeline.time.monotonic", return_value=1):
                    self.assertEqual(client._network("GET", "/api/v2/users"), {"users": []})
                self.assertIn(unittest.mock.call(60), sleep.call_args_list)
                self.assertEqual(client.next_request, 4)
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()
