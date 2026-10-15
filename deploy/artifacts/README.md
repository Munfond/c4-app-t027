# Cloud demo perception outputs

`perception-mini-val.zip` contains **324 actual precomputed JSON outputs**: Radar,
BEV Occupancy, Flow and Seg3D for the same **81 mini_val frames** as the frame catalog.
These are the existing outputs from `scripts/export_perception.py`, with their
sensor coordinates, source and checkpoint hashes unchanged. They contain no raw
nuScenes files, camera images, passwords or model weights. Seg3D is an experimental SalsaNext transfer prediction; it is not validated nuScenes accuracy.

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

## Frozen native PPO playback

`native-ppo-demo.zip` contains 226 checksum-bound files: the paired baseline/PPO
20-frame captures, simulator RGB/RAW/reference/prediction artifacts, frozen policy,
training/audit manifests and the occupancy checkpoint used to verify provenance.
It contains no `.env`, credentials, nuScenes raw media, simulator runtime or job queue.
Only simulator images are included here. Installing does not execute the checkpoint.

Docker installs both archives automatically. The public `/api/v1/evidence/*` GET
routes serve validated recordings on CPU; interactive `/experiments` stays opt-in.
For an existing deployment, install into a fresh root and configure the artifact
roots from `docs/MVP_USER_GUIDE.vi.md`:

```bash
python scripts/native_demo_bundle.py --destination /path/to/restored-root
```

The installer validates paths, limits, hashes and existing files before writing.
It refuses to overwrite changed artifacts. The service independently validates
reports, policy/checkpoint hashes and each requested frame. A seal verifies local
integrity; it is not an independent certification of model quality.
