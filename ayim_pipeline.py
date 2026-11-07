"""Fetch osu! ranked/loved data and export the existing AYIM dashboard schema.

Dates are UTC, inclusive calendar dates. Secrets are loaded from .env/env vars.
Run: python ayim_pipeline.py --start 2026-01-01 --end 2026-10-23
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import time

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("ayim")
MODE = {"0": "osu!", "1": "osu!taiko", "2": "osu!catch", "3": "osu!mania"}
GENRE = dict(zip(map(str, [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14]),
                 ["Unspecified", "Video Game", "Anime", "Rock", "Pop", "Other",
                  "Novelty", "Hip Hop", "Electronic", "Metal", "Classical", "Folk", "Jazz"]))
LANGUAGE = dict(zip(map(str, range(1, 15)),
                    ["Unspecified", "English", "Japanese", "Chinese", "Instrumental",
                     "Korean", "French", "German", "Swedish", "Spanish", "Italian",
                     "Russian", "Polish", "Other"]))
DIFFICULTY_COLUMNS = ["mode", "beatmapset_id", "beatmap_id", "genre_id", "language_id",
                      "status", "title_unicode", "artist_unicode", "approved_date", "version",
                      "difficulty_rating", "creator_id", "gder_id", "gd", "favourite_count",
                      "playcount", "is_new", "country", "mapper"]
SET_COLUMNS = ["mode", "beatmapset_id", "beatmap_count", "title", "artist", "mapper",
               "mapper_id", "approved_date", "favourite_count", "playcount", "genre",
               "language", "country", "status", "new_mapper"]


def load_credentials(path: Path = ROOT / ".env") -> dict[str, str]:
    """Read a small KEY=VALUE file without executing its contents."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    names = ["OSU_API_KEY", "OSU_CLIENT_ID", "OSU_CLIENT_SECRET"]
    values = {name: os.environ.get(name, values.get(name, "")) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("Missing credentials: " + ", ".join(missing))
    return values


def bounds(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("Start date must not follow end date")
    return pd.Timestamp(first, tz="UTC"), pd.Timestamp(last + timedelta(days=1), tz="UTC")


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class OsuClient:
    """One connection pool/token, persistent public-response cache and global pacing.

    Neither the cache nor errors contain request URLs, API keys or access tokens.
    All network attempts, including retries and OAuth, share the rate limiter.
    """

    def __init__(self, credentials, cache_path=ROOT / ".cache" / "responses.sqlite3",
                 refresh=False, cache_hours=24):
        self.credentials = credentials
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "AYIM/2026"})
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, fetched REAL, body TEXT)")
        self.refresh, self.cache_seconds = refresh, cache_hours * 3600
        self.token, self.token_expiry, self.next_request = None, 0, 0
        self.requests, self.cache_hits = Counter(), Counter()
        self.source_times = []

    def close(self):
        self.session.close()
        self.db.close()

    def _network(self, method, path, **kwargs):
        for attempt in range(5):
            time.sleep(max(0, self.next_request - time.monotonic()))
            # /users charges quota per requested ID, rather than per batch.
            interval = 3.0 if path == "/api/v2/users" else 1.05
            self.next_request = time.monotonic() + interval
            self.requests[path] += 1
            try:
                response = self.session.request(method, "https://osu.ppy.sh" + path,
                                                timeout=(10, 60), **kwargs)
            except requests.RequestException:
                if attempt == 4:
                    raise RuntimeError(f"Network failure after retries: {path}") from None
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 4:
                    raise RuntimeError(f"HTTP {response.status_code} after retries: {path}")
                try:
                    retry_after = float(response.headers.get("Retry-After", 0))
                except ValueError:
                    try:
                        retry_after = parsedate_to_datetime(response.headers["Retry-After"]).timestamp() - time.time()
                    except (ValueError, TypeError, KeyError):
                        retry_after = 0
                delay = max(retry_after, 60 if response.status_code == 429 else min(2 ** attempt, 30))
                LOG.warning("HTTP %d on %s; retry in %.0f seconds", response.status_code, path, delay)
                time.sleep(delay)
                continue
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status_code}: {path}")
            try:
                data = response.json()
            except ValueError:
                raise RuntimeError(f"Non-JSON response: {path}") from None
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"API returned an error: {path}")
            return data
        raise AssertionError("Unreachable")

    def _authorize(self):
        if self.token and time.time() < self.token_expiry:
            return
        data = self._network("POST", "/oauth/token", json={
            "client_id": int(self.credentials["OSU_CLIENT_ID"]),
            "client_secret": self.credentials["OSU_CLIENT_SECRET"],
            "grant_type": "client_credentials", "scope": "public"})
        self.token = data["access_token"]
        self.token_expiry = time.time() + data["expires_in"] - 60

    def get(self, path, params=None, v1=False):
        params = params or {}
        key = hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
        cached = self.db.execute("SELECT fetched, body FROM responses WHERE key=?", (key,)).fetchone()
        if cached and not self.refresh and time.time() - cached[0] < self.cache_seconds:
            self.cache_hits[path] += 1
            self.source_times.append(cached[0])
            return json.loads(cached[1])
        if v1:
            data = self._network("GET", path, params={**params, "k": self.credentials["OSU_API_KEY"]})
        else:
            self._authorize()
            try:
                data = self._network("GET", path, params=params,
                                     headers={"Authorization": "Bearer " + self.token})
            except RuntimeError as error:
                if "HTTP 401:" not in str(error):
                    raise
                self.token = None
                self._authorize()
                data = self._network("GET", path, params=params,
                                     headers={"Authorization": "Bearer " + self.token})
        fetched = time.time()
        self.db.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?)",
                        (key, fetched, json.dumps(data)))
        self.db.commit()
        self.source_times.append(fetched)
        return data


def fetch_period(client, start: str, end: str) -> pd.DataFrame:
    first, exclusive_end = bounds(start, end)
    # Overlap by one second so difficulties with the same approval timestamp
    # cannot fall between pages, regardless of inclusive/exclusive API behavior.
    cursor = first - pd.Timedelta(seconds=1)
    rows = {}
    for page in range(10000):
        batch = client.get("/api/get_beatmaps", {
            "since": cursor.strftime("%Y-%m-%d %H:%M:%S"), "limit": 500}, v1=True)
        if not isinstance(batch, list):
            raise ValueError("Expected a beatmap array")
        if not batch:
            break
        dates = pd.to_datetime([x["approved_date"] for x in batch], utc=True)
        if dates.isna().any() or not dates.is_monotonic_increasing:
            raise ValueError("API pagination dates are missing or not ordered")
        for item, approved in zip(batch, dates):
            if first <= approved < exclusive_end and str(item["approved"]) in {"1", "4"}:
                rows[str(item["beatmap_id"])] = item
        LOG.info("Listing page %d: %s, %d unique difficulties", page + 1, dates.max(), len(rows))
        if dates.max() >= exclusive_end or len(batch) < 500:
            break
        next_cursor = dates.max() - pd.Timedelta(seconds=1)
        if next_cursor <= cursor:
            # Never silently advance past a saturated timestamp and lose maps.
            raise RuntimeError("500-row timestamp boundary saturated; cannot prove complete pagination")
        cursor = next_cursor
    else:
        raise RuntimeError("Pagination safety limit reached")
    if not rows:
        raise ValueError("No Rank/Love difficulties returned for requested period")
    return pd.DataFrame(rows.values()).sort_values(["approved_date", "beatmapset_id", "beatmap_id"]).reset_index(drop=True)


def chunks(items, size=50):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_owners(client, ids):
    owners = {}
    for i, group in enumerate(chunks(sorted(set(map(int, ids))))):
        data = client.get("/api/v2/beatmaps", {"ids[]": group})
        owners.update({str(b["id"]): str(b["user_id"]) for b in data["beatmaps"]})
        if i % 20 == 0:
            LOG.info("Difficulty authors: %d / %d", len(owners), len(ids))
    missing = set(map(str, ids)) - owners.keys()
    if missing:
        raise ValueError(f"Missing author metadata for {len(missing)} difficulties")
    return owners


def fetch_users(client, ids):
    users = {}
    unique_ids = sorted(set(map(int, ids)))
    for index, group in enumerate(chunks(unique_ids), 1):
        data = client.get("/api/v2/users", {"ids[]": group})
        users.update({str(u["id"]): {"mapper": u["username"], "country": u["country_code"]}
                      for u in data["users"]})
        if index % 10 == 0:
            LOG.info("User profiles: %d / %d", min(index * 50, len(unique_ids)), len(unique_ids))
    # Deleted/restricted users can be absent: retain null, never guess country/name.
    return users


def mapper_is_new(client, user_id, year):
    """First *hosted ranked/approved* set is in this year, all modes combined.

    Preserve the original host-level definition; guest difficulties and Loved
    alone do not establish a ranked debut. Exhaust history before returning True.
    """
    offset, has_this_year = 0, False
    seen_pages = set()
    while True:
        try:
            data = client.get(f"/api/v2/users/{int(user_id)}/beatmapsets/ranked",
                              {"limit": 100, "offset": offset})
        except RuntimeError as error:
            if "HTTP 404:" in str(error):
                return None
            raise
        if not isinstance(data, list):
            raise ValueError("Expected ranked beatmapset history array")
        fingerprint = tuple(x["id"] for x in data)
        if fingerprint and fingerprint in seen_pages:
            raise RuntimeError("Ranked history pagination did not advance")
        seen_pages.add(fingerprint)
        for item in data:
            ranked = item.get("ranked_date")
            if not ranked:
                raise ValueError("Ranked history contains a missing ranked_date")
            ranked_year = pd.Timestamp(ranked).year
            if ranked_year < year:
                return False
            has_this_year |= ranked_year == year
        if len(data) < 100:
            return bool(has_this_year)
        offset += len(data)


def classify_hosts(client, hosts, year, output):
    """Use recent ranked metadata as proof of an older debut before user lookups.

    A historical hosted Ranked set conclusively proves False. Absence proves
    nothing, so all remaining hosts still receive a fully paginated history check.
    Two recent years cost about 100 listing calls instead of thousands of users.
    """
    newcomers = {}
    remaining = set(hosts)
    for previous in [year - 1, year - 2]:
        if not remaining:
            break
        historical = fetch_period(client, f"{previous}-01-01", f"{previous}-12-31")
        old_hosts = set(historical.loc[historical["approved"].astype(str).eq("1"), "creator_id"].astype(str))
        proven_old = remaining & old_hosts
        newcomers.update({uid: False for uid in proven_old})
        remaining -= proven_old
        LOG.info("%d Ranked metadata proves %d existing hosts; %d histories remain", previous, len(proven_old), len(remaining))
        atomic_json(output / "mapper_new_status.json", newcomers)
    LOG.info("Checking full ranked history for %d remaining hosts", len(remaining))
    for index, uid in enumerate(sorted(remaining, key=int), 1):
        newcomers[uid] = mapper_is_new(client, uid, year)
        if index % 25 == 0 or index == len(remaining):
            LOG.info("Mapper history: %d / %d (total hosts %d)", index, len(remaining), len(hosts))
            atomic_json(output / "mapper_new_status.json", newcomers)
    return newcomers


def clean(raw: pd.DataFrame, owners, users, newcomers):
    frame = raw.copy()
    for col in ["beatmap_id", "beatmapset_id", "creator_id", "mode", "approved", "genre_id", "language_id"]:
        frame[col] = frame[col].astype(str)
    frame["gder_id"] = frame["beatmap_id"].map(owners)
    frame["gd"] = frame["creator_id"].ne(frame["gder_id"]).astype("int64")
    frame["is_new"] = frame["creator_id"].map(newcomers).astype("boolean")
    # Keep the raw CSV's API IDs/strings, before display-label conversion.
    enriched = raw.copy()
    for col in ["gder_id", "gd", "is_new"]:
        enriched[col] = frame[col]
    frame["mode"] = frame["mode"].map(MODE)
    frame["status"] = frame["approved"].map({"1": "Rank", "4": "Love"})
    frame["genre_id"] = frame["genre_id"].map(GENRE).fillna("Unspecified")
    frame["language_id"] = frame["language_id"].map(LANGUAGE).fillna("Unspecified")
    stars = pd.to_numeric(frame["difficultyrating"], errors="raise")
    if stars.isna().any() or (~stars.map(math.isfinite)).any() or stars.lt(0).any():
        raise ValueError("Invalid difficulty stars")
    frame["difficulty_rating"] = pd.cut(stars, [-float("inf"), 2, 2.7, 4, 5.3, 6.5, float("inf")],
                                         right=False, labels=["Easy", "Normal", "Hard", "Insane", "Expert", "Expert+"])
    for unicode_col, fallback in [("title_unicode", "title"), ("artist_unicode", "artist")]:
        frame[unicode_col] = frame[unicode_col].replace("", pd.NA).fillna(frame[fallback])
    for col in ["beatmapset_id", "beatmap_id", "creator_id", "gder_id", "favourite_count", "playcount"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise").astype("int64")
    frame["approved_date"] = pd.to_datetime(frame["approved_date"], utc=True).dt.tz_localize(None)
    for col in ["country", "mapper"]:
        frame[col] = frame["gder_id"].astype(str).map(lambda uid: users.get(uid, {}).get(col))
    detail = frame[DIFFICULTY_COLUMNS].copy()
    sets = detail.groupby(["beatmapset_id", "mode"], observed=True, dropna=False, as_index=False).agg(
        beatmap_count=("beatmap_id", "size"), status=("status", "first"), genre=("genre_id", "first"),
        language=("language_id", "first"), title=("title_unicode", "first"), artist=("artist_unicode", "first"),
        mapper_id=("creator_id", "first"), approved_date=("approved_date", "min"),
        favourite_count=("favourite_count", "max"), playcount=("playcount", "sum"))
    # Look up the host separately, even when they did not author any difficulty.
    for col in ["country", "mapper"]:
        sets[col] = sets["mapper_id"].astype(str).map(lambda uid: users.get(uid, {}).get(col))
    sets["new_mapper"] = sets["mapper_id"].astype(str).map(newcomers).astype("boolean")
    sets = sets[SET_COLUMNS].sort_values(["approved_date", "beatmapset_id", "mode"]).reset_index(drop=True)
    return enriched, detail, sets


def validate(detail, sets, start, end):
    first, last = bounds(start, end)
    if detail["beatmap_id"].duplicated().any():
        raise ValueError("Duplicate beatmap_id")
    if sets.duplicated(["beatmapset_id", "mode"]).any():
        raise ValueError("Duplicate set/mode")
    for frame in [detail, sets]:
        dates = pd.to_datetime(frame["approved_date"], utc=True)
        if not ((dates >= first) & (dates < last)).all():
            raise ValueError("Output dates outside requested range")
        if frame[["mode", "status"]].isna().any().any():
            raise ValueError("Unmapped mode/status")
    if int(sets["beatmap_count"].sum()) != len(detail):
        raise ValueError("Difficulty counts do not reconcile")
    if int(sets["playcount"].sum()) != int(detail["playcount"].sum()):
        raise ValueError("Play counts do not reconcile")
    # Every set-level attribute must agree inside each set/mode group.
    for column in ["creator_id", "status", "genre_id", "language_id", "title_unicode", "artist_unicode", "favourite_count"]:
        if (detail.groupby(["beatmapset_id", "mode"])[column].nunique(dropna=False) > 1).any():
            raise ValueError(f"Inconsistent set metadata: {column}")


def run(start="2026-01-01", end="2026-10-23", output_dir=None, refresh=False):
    first, _ = bounds(start, end)
    if date.fromisoformat(start).year != date.fromisoformat(end).year:
        raise ValueError("Run one calendar year at a time for new_mapper classification")
    output = Path(output_dir) if output_dir else ROOT / "outputs" / f"{start}_{end}"
    output.mkdir(parents=True, exist_ok=True)
    client = OsuClient(load_credentials(), refresh=refresh)
    started = datetime.now(timezone.utc)
    try:
        raw = fetch_period(client, start, end)
        atomic_json(output / "source_beatmaps.json", raw.to_dict(orient="records"))
        owners = fetch_owners(client, raw["beatmap_id"].tolist())
        hosts = sorted(set(raw["creator_id"].astype(str)), key=int)
        users = fetch_users(client, set(hosts) | set(owners.values()))
        newcomers = classify_hosts(client, hosts, first.year, output)
        enriched, detail, sets = clean(raw, owners, users, newcomers)
        validate(detail, sets, start, end)
        tag = f"{start.replace('-', '')}_{end.replace('-', '')}"
        paths = {"raw": output / f"ayim_raw_{tag}.csv", "difficulties": output / f"ayim{first.year}_gd_{tag}.csv",
                 "beatmapsets": output / f"ayim{first.year}_{tag}.csv"}
        for name, frame in [("raw", enriched), ("difficulties", detail), ("beatmapsets", sets)]:
            tmp = paths[name].with_suffix(".csv.tmp")
            frame.to_csv(tmp, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S")
            tmp.replace(paths[name])
        finished = datetime.now(timezone.utc)
        manifest = {
            "requested_start": start, "requested_end_inclusive": end, "date_timezone": "UTC",
            "started_at_utc": started.isoformat(), "finished_at_utc": finished.isoformat(),
            "source_response_earliest_utc": datetime.fromtimestamp(min(client.source_times), timezone.utc).isoformat(),
            "source_response_latest_utc": datetime.fromtimestamp(max(client.source_times), timezone.utc).isoformat(),
            "end_day_not_yet_complete_utc": finished.date() <= date.fromisoformat(end),
            "difficulties": len(detail), "unique_beatmapsets": int(sets.beatmapset_id.nunique()),
            "beatmapset_mode_rows": len(sets), "hosts": len(hosts),
            "difficulty_authors": len(set(owners.values())), "new_hosts": sum(x is True for x in newcomers.values()),
            "unknown_new_host_status": sum(x is None for x in newcomers.values()),
            "missing_host_profiles": len(set(hosts) - users.keys()),
            "missing_author_profiles": len(set(owners.values()) - users.keys()),
            "first_approved_utc": str(detail.approved_date.min()), "last_approved_utc": str(detail.approved_date.max()),
            "difficulty_counts": detail.groupby(["mode", "status"]).size().to_dict(),
            "files": {name: str(path.resolve()) for name, path in paths.items()},
            "sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
            "network_requests": sum(client.requests.values()), "cache_hits": sum(client.cache_hits.values()),
            "validation": "passed", "new_mapper_definition": "First hosted ranked/approved beatmapset is in requested year, all modes; Loved/GD alone excluded",
            "limitations": ["Counts are current API counters, not a historical end-date snapshot.",
                            "Set rows are per (beatmapset_id, mode); favourites repeat across modes.",
                            "gder_id uses the primary user_id for dashboard compatibility; co-owners are not exploded.",
                            "Deleted/restricted profiles remain null."]}
        manifest["difficulty_counts"] = {f"{mode} / {status}": int(n) for (mode, status), n in manifest["difficulty_counts"].items()}
        atomic_json(output / "manifest.json", manifest)
        LOG.info("Done: %d difficulties, %d unique sets; output %s", len(detail), sets.beatmapset_id.nunique(), output)
        return {"raw": enriched, "difficulties": detail, "beatmapsets": sets, "manifest": manifest}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-10-23")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached responses")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        run(args.start, args.end, args.output_dir, args.refresh)
    except (ValueError, RuntimeError) as error:
        LOG.error("Pipeline stopped: %s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
