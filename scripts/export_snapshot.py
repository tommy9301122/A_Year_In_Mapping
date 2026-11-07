"""Validate a pipeline run and publish only the public fields required by the website."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from ayim_pipeline import validate, atomic_json


def export(folder, target, final=False):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['validation'] != 'passed':
        raise ValueError('Pipeline validation did not pass')
    frames = {}
    for name in ('difficulties', 'beatmapsets'):
        # Manifests can move between machines: resolve by basename within the run.
        path = folder / manifest['files'][name].replace('\\', '/').split('/')[-1]
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise ValueError('Source hash mismatch: ' + name)
        frames[name] = pd.read_csv(path)
    detail, sets = frames['difficulties'], frames['beatmapsets']
    start, end = manifest['requested_start'], manifest['requested_end_inclusive']
    validate(detail, sets, start, end)
    year = int(start[:4])
    if final and (start != f'{year}-01-01' or end != f'{year}-12-31'
                  or manifest['end_day_not_yet_complete_utc']
                  or datetime.fromisoformat(manifest['source_response_earliest_utc']) < datetime(year + 1, 1, 1, tzinfo=timezone.utc)):
        raise ValueError('Final requires a complete calendar year and all source responses after year end; use --refresh')
    set_columns = ['mode', 'beatmapset_id', 'title', 'artist', 'mapper', 'mapper_id', 'country',
                   'status', 'new_mapper', 'genre', 'language', 'favourite_count', 'playcount', 'beatmap_count']
    detail_columns = ['mode', 'beatmapset_id', 'beatmap_id', 'gder_id', 'mapper', 'country', 'playcount', 'gd']
    data = {'meta': {'year': year, 'start': start, 'end': end, 'release': 'final' if final else 'preview',
                    'fetchedAt': manifest['source_response_latest_utc'], 'timezone': 'UTC',
                    'sourceSha256': manifest['sha256'], 'limitations': manifest['limitations']},
            'setColumns': set_columns, 'sets': json.loads(sets[set_columns].to_json(orient='values', force_ascii=False)),
            'detailColumns': detail_columns, 'details': json.loads(detail[detail_columns].to_json(orient='values', force_ascii=False))}
    atomic_json(target, data)
    print(f'Exported {len(detail)} difficulties / {sets.beatmapset_id.nunique()} sets ({data["meta"]["release"]})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'snapshot.json')
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    export(args.folder, args.output, args.final)
