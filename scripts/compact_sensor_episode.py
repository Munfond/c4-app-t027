"""Create a new lossless compact episode. Original capture and predictions stay intact."""
import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.active_sensing.episode_inputs import RawEpisode  # noqa: E402
from src.simulation.carla_rig import COMPACT_STORAGE, point_arrays, sha256_file, verify_episode  # noqa: E402


def compact(source, output):
    episode = RawEpisode(source)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Output exists; never overwrite capture data')
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < episode.manifest['artifact_bytes'] * 1.2 + 1024 ** 3:
        raise ValueError('Insufficient conversion headroom; source capture is unchanged')
    output.mkdir(parents=True)
    manifest = copy.deepcopy(episode.manifest)
    manifest.update(schema_version=2, storage_encoding=COMPACT_STORAGE,
                    derivation={'kind': 'lossless_storage_conversion',
                                'source_manifest_sha256': episode.verification['manifest_sha256']})
    manifest['rig_options']['storage_encoding'] = COMPACT_STORAGE
    if manifest.get('environment_inventory'):
        source_inventory = episode._artifact(manifest['environment_inventory'], 'ground_truth')
        inventory_path = output / manifest['environment_inventory']['path']
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_inventory, inventory_path)
    total = original = 0

    def artifact(path):
        return {'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size,
                'sha256': sha256_file(path)}

    for frame in manifest['frames']:
        metadata = json.loads(episode._artifact(frame['metadata'], '').read_text())
        for name, sensor in metadata['sensors'].items():
            source_path = episode._artifact(sensor['artifact'], 'ground_truth' if name.startswith('GT_') else 'inputs')
            original += source_path.stat().st_size
            path = output / sensor['artifact']['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.suffix == '.npz':
                raw, old_ego = point_arrays(source_path, sensor, np.asarray(metadata['ego_ground_to_world_carla']), episode.storage)
                np.savez_compressed(path, raw=raw)
                new_raw, new_ego = point_arrays(path, sensor, np.asarray(metadata['ego_ground_to_world_carla']), COMPACT_STORAGE)
                if not np.array_equal(new_raw, raw) or not np.array_equal(new_ego, old_ego):
                    raise ValueError('Point storage conversion changed decoded data')
            elif source_path.suffix == '.npy':
                path = path.with_suffix('.png')
                tags = np.load(source_path, allow_pickle=False)
                Image.fromarray(tags).save(path, format='PNG')
                with Image.open(path) as image:
                    if not np.array_equal(np.asarray(image), tags):
                        raise ValueError('Semantic storage conversion changed tag IDs')
            else:
                shutil.copy2(source_path, path)  # RGB PNG bytes preserved, no JPEG conversion.
            sensor['artifact'] = artifact(path)
            total += path.stat().st_size
        gt_source = episode._artifact(metadata['actor_ground_truth'], 'ground_truth')
        gt_path = output / metadata['actor_ground_truth']['path']
        shutil.copy2(gt_source, gt_path)
        metadata['actor_ground_truth'] = artifact(gt_path)
        meta_path = output / frame['metadata']['path']
        meta_path.write_text(json.dumps(metadata, indent=2, allow_nan=False))
        frame['metadata'] = artifact(meta_path)
    manifest['artifact_bytes'] = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
    manifest['storage_conversion'] = {'source_sensor_bytes': original, 'compact_sensor_bytes': total,
                                      'sensor_bytes_reduction_fraction': 1 - total / original,
                                      'decoded_point_and_semantic_arrays_exact': True, 'rgb_bytes_unchanged': True}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
    try:
        report = verify_episode(output)
    except BaseException:
        (output / 'manifest.json').replace(output / 'manifest.failed.json')
        raise
    return report | manifest['storage_conversion']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compact(args.episode, args.output), indent=2))
