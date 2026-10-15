"""Positive-target geometry diagnostic for incomplete CARLA actor ground truth.

Not nuScenes mAP, class-aware recall, precision, safety certification or RL reward.
Unknown extra predictions cannot be counted as false positives with partial GT.
"""
import math

import numpy as np


def geometry(box):
    center = np.asarray(box['center_ego'], dtype=float)
    size = np.asarray(box['size_lwh'], dtype=float)
    rotation = np.asarray(box['rotation_ego'], dtype=float)
    if (center.shape != (3,) or size.shape != (3,) or rotation.shape != (3, 3)
            or not np.isfinite(center).all() or not np.isfinite(size).all()
            or not np.isfinite(rotation).all() or (size <= 0).any()
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-4)
            or not np.isclose(np.linalg.det(rotation), 1, atol=1e-4)):
        raise ValueError('Invalid box geometry')
    return center, size


def target_diagnostic(truth, predictions, radius_m=54., center_gate_m=2., threshold=.3):
    for value in (radius_m, center_gate_m):
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Radius and center gate must be positive finite values')
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid score threshold')
    ids = [box['actor_id'] for box in truth]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate reference actor IDs')
    references = []
    for box in truth:
        center, _ = geometry(box)
        if type(box['semantic_lidar_visible']) is not bool:
            raise ValueError('Visibility must be explicitly measured')
        # Broad spawned vehicle/person target set. Class labels do NOT gate this diagnostic.
        if (box['type_id'].startswith(('vehicle.', 'walker.pedestrian.'))
                and box['semantic_lidar_visible'] and np.linalg.norm(center[:2]) <= radius_m):
            references.append(box)
    selected = []
    for index, box in enumerate(predictions):
        geometry(box)
        score = float(box['score'])
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid prediction score')
        if score >= threshold:
            selected.append((index, box))
    # Augmenting paths maximize one-to-one cardinality. A greedy nearest-edge match
    # can undercount targets in crowded scenes. Within each path, try closest first.
    edges = []
    for reference in references:
        center, _ = geometry(reference)
        distances = [(float(np.linalg.norm(center[:2] - geometry(box)[0][:2])), j)
                     for j, (_, box) in enumerate(selected)]
        edges.append([j for distance, j in sorted(distances) if distance <= center_gate_m])
    owners = {}

    def assign(i, visited):
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in owners or assign(owners[j], visited):
                owners[j] = i
                return True
        return False

    for i in range(len(references)):
        assign(i, set())
    matched = []
    for j, i in sorted(owners.items(), key=lambda pair: pair[1]):
        reference, (prediction_index, box) = references[i], selected[j]
        center, size = geometry(reference)
        p_center, p_size = geometry(box)
        matched.append({'actor_id': reference['actor_id'], 'reference_type': reference['type_id'],
                        'prediction_index': prediction_index, 'predicted_class': box['class_name'],
                        'center_xy_error_m': float(np.linalg.norm(center[:2] - p_center[:2])),
                        'height_center_error_m': float(abs(center[2] - p_center[2])),
                        'size_absolute_error_lwh_m': abs(size - p_size).tolist()})
    matched_ids = {row['actor_id'] for row in matched}
    return {'required_targets': len(references), 'matched_targets': len(matched),
            'positive_target_geometry_recall': len(matched) / len(references) if references else None,
            'matches': matched,
            'unmatched_actor_ids': [box['actor_id'] for box in references if box['actor_id'] not in matched_ids],
            'unmatched_predictions_unclassified': len(selected) - len(matched),
            'false_positives': None, 'precision': None,
            'matching': 'class-agnostic maximum-cardinality 1:1 XY center-distance',
            'radius_m': radius_m, 'center_gate_m': center_gate_m, 'threshold': threshold,
            'reference_scope': 'visible spawned vehicle/person actors only; incomplete scene GT',
            'validated_detection_quality': False, 'usable_for_rl_reward': False}
