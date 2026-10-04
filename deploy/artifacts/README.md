# Cloud demo perception outputs

`perception-mini-val.zip` contains **243 actual precomputed JSON outputs**: Radar,
BEV Occupancy and Flow for the same **81 mini_val frames** as the frame catalog.
These are the existing outputs from `scripts/export_perception.py`, with their
sensor coordinates, source and checkpoint hashes unchanged. They contain no raw
nuScenes files, camera images, passwords or model weights. Seg3D remains unavailable.

The backend Docker build installs this small archive into
`data/lab/cache/perception`. The installer verifies each byte count/SHA256 and the
complete token/task matrix before writing. It refuses to replace a different
existing cache. API schema validation still applies when outputs are requested.

Regenerate after exporting a new **scene-aligned** dataset:

```powershell
.\.venv-lab\Scripts\python.exe scripts/perception_bundle.py pack --lab-root data/lab
```

For a native deployment, or a volume that hides the image's `data/lab` directory:

```powershell
.\.venv-lab\Scripts\python.exe scripts/perception_bundle.py install --destination 'C:/apps/lab/cache/perception'
```

This is deployment packaging, not new training or a new accuracy evaluation.
