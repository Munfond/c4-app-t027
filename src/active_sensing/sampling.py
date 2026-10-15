"""One deterministic point gate for runtime and measured detector replay."""
import math

import numpy as np

SAMPLING_ABI = 'numpy-default-rng-sorted-subset-v1'


def subset_indices(length, keep, seed):
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise ValueError('Point count must be a nonnegative integer')
    if not math.isfinite(keep) or not 0 < keep <= 1:
        raise ValueError('keep must be in (0,1]')
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('Sampling seed must be a nonnegative integer')
    count = max(1, math.ceil(length * keep)) if length else 0
    if count == length:
        return np.arange(length)
    return np.sort(np.random.default_rng(seed).choice(length, size=count, replace=False))
