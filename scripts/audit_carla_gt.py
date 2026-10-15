"""Inspect annotation coverage and actual sensor returns; never produce RL rewards."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from src.active_sensing.detection_diagnostic import geometry  # noqa: E402
from src.active_sensing.episode_inputs import RawEpisode  # noqa: E402
from src.active_sensing.sampling import SAMPLING_ABI, subset_indices  # noqa: E402
from src.simulation.carla_rig import point_arrays  # noqa: E402

# Values inspected from the installed CARLA 0.9.16 CityObjectLabel enum.
# Earlier CARLA taxonomies use different integers: refuse unknown server versions.
TARGET_TAGS = {'Pedestrians': 12, 'Rider': 13, 'Car': 14, 'Truck': 15,
               'Bus': 16, 'Motorcycle': 18, 'Bicycle': 19}


def box_return_counts(points, boxes):
    points = np.asarray(points)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('Expected finite ego-frame XYZ')
    result = {}
    for box in boxes:
        center, size = geometry(box)
        # Column-vector box->ego rotation; row-vector inverse is multiply by R.
        local = (points - center) @ np.asarray(box['rotation_ego'])
        result[box['actor_id']] = int(np.count_nonzero(np.all(abs(local) <= size / 2 + 1e-5, axis=1)))
    return result


def audit(episode_root, seed=7):
    episode = RawEpisode(episode_root)
    if not str(episode.manifest['server_version']).startswith('0.9.16'):
        raise ValueError('Semantic taxonomy requires CARLA 0.9.16')
    rows = []
    unknown_ids = set()
    no_32 = no_64 = 0
    for ref in episode.manifest['frames']:
        meta = json.loads(episode._artifact(ref['metadata'], '').read_text())
        gt = json.loads(episode._artifact(meta['actor_ground_truth'], 'ground_truth').read_text())
        boxes = [box for box in gt['boxes'] if box['type_id'].startswith(('vehicle.', 'walker.pedestrian.'))]
        known = {box['actor_id'] for box in boxes} | {episode.manifest['ego_actor_id']}
        counts = {}
        for name in ('LIDAR_TOP', 'LIDAR_TOP_64'):
            sensor = meta['sensors'].get(name)
            if sensor is None:
                continue
            _, points = point_arrays(episode._artifact(sensor['artifact'], 'inputs'), sensor,
                                     np.asarray(meta['ego_ground_to_world_carla']), episode.storage)
            counts[name] = box_return_counts(points, boxes)
            counts[name + '_keep_50'] = box_return_counts(
                points[subset_indices(len(points), .5, seed + ref['frame_id'])], boxes)
        sensor = meta['sensors']['GT_LIDAR']
        with np.load(episode._artifact(sensor['artifact'], 'ground_truth'), allow_pickle=False) as data:
            raw = data['raw']
            target = np.isin(raw['tag'], list(TARGET_TAGS.values()))
            ids, n = np.unique(raw['object'][target], return_counts=True)
            semantic_counts = dict(zip(map(int, ids), map(int, n)))
        unannotated = sorted(set(semantic_counts) - known)
        unknown_ids.update(unannotated)
        targets = []
        for box in boxes:
            actor_id = box['actor_id']
            row = {'actor_id': actor_id, 'type_id': box['type_id'],
                   'radius_xy_m': float(np.linalg.norm(box['center_ego'][:2])),
                   'reference_semantic_hits': semantic_counts.get(actor_id, 0),
                   'input_box_return_counts': {name: value[actor_id] for name, value in counts.items()}}
            if row['reference_semantic_hits'] > 0:
                no_32 += counts['LIDAR_TOP'][actor_id] == 0
                no_64 += ('LIDAR_TOP_64' in counts and counts['LIDAR_TOP_64'][actor_id] == 0)
            targets.append(row)
        rows.append({'frame_id': ref['frame_id'], 'timestamp': ref['timestamp'], 'targets': targets,
                     'unannotated_semantic_target_ids': unannotated,
                     'unannotated_semantic_target_returns': sum(semantic_counts[i] for i in unannotated)})
    return {'kind': 'CARLA_GT_coverage_and_sensor_return_audit',
            'capture_manifest_sha256': episode.verification['manifest_sha256'],
            'actor_annotation_scope': episode.manifest.get('actor_annotation_scope', 'episode_spawned_actors'),
            'environment_inventory_reference': episode.manifest.get('environment_inventory'),
            'server_version': episode.manifest['server_version'], 'semantic_taxonomy': TARGET_TAGS,
            'taxonomy_source': 'https://carla.readthedocs.io/en/0.9.16/ref_sensors/#semantic-segmentation-camera',
            'sampling_abi': SAMPLING_ABI, 'sampling_seed': seed, 'frames': rows,
            'unannotated_semantic_target_ids': sorted(unknown_ids),
            'reference_visible_instances_without_32_box_returns': int(no_32),
            'reference_visible_instances_without_64_box_returns': int(no_64),
            'scene_precision_ready': False, 'usable_for_rl_reward': False,
            'limitations': [
                'Zero unannotated semantic IDs only covers surfaces hit by the independent semantic reference',
                'Environment mesh inventory, if present, still requires semantic ID mapping and deduplication; actor boxes do not establish complete scene ontology',
                'Input points inside engine boxes are geometric counts, not aligned semantic labels or guaranteed detectability',
                'Reference visibility does not establish chosen-sensor observability; keep all denominators explicit',
                'No class-aware metric, new-target latency or complete scene false-positive judgment',
                'GT audit stays on the evaluator side; never an actor observation feature']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; use a new file')
    result = audit(args.episode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({key: value for key, value in result.items() if key != 'frames'}, indent=2))
