"""Real PPO updates on sealed measured occupancy-proxy outcomes; isolated scene test."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.callbacks import BaseCallback  # noqa: E402

from src.active_sensing.occupancy_proxy import OBSERVATION_ABI, OccupancyProxyEnv, load_dataset  # noqa: E402


def policy_digest(model):
    h = hashlib.sha256()
    for name, tensor in sorted(model.policy.state_dict().items()):
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def evaluate(data, split, model=None, fixed=None, threshold=None):
    env = OccupancyProxyEnv(data, split)
    logs, scene_rewards = [], []
    for e in range(len(env.episodes)):
        obs, _ = env.reset(options={"episode": e})
        done = False
        rewards = []
        while not done:
            if model is not None:
                action, _ = model.predict(obs, deterministic=True)
                action = int(action)
            elif fixed is not None:
                action = fixed
            else:
                # Rule threshold fitted on sensor density in TRAIN only; no GT teacher.
                action = 0 if obs[0] < threshold else 1
            row = env.episode["steps"][env.index]
            confusion = row["outcomes"][action]["confusion"]
            obs, reward, done, _, info = env.step(action)
            rewards.append(reward)
            logs.append(
                {
                    "scene": env.episode["scene"],
                    "token": row["token"],
                    "action": action,
                    "reward": reward,
                    "confusion": confusion,
                    **info,
                }
            )
        scene_rewards.append(float(np.mean(rewards)))
    cm = np.asarray([r["confusion"] for r in logs]).sum(axis=0)
    tp = int(cm[1:, 1:].sum())
    union = int(cm[1:, :].sum() + cm[:, 1:].sum() - tp)
    object_union = int(cm[2, :].sum() + cm[:, 2].sum() - cm[2, 2])
    metrics = {
        "frames": len(logs),
        "scenes": len(scene_rewards),
        "mean_scene_reward": float(np.mean(scene_rewards)),
        "occupied_iou": tp / union if union else None,
        "object_iou": int(cm[2, 2]) / object_union if object_union else None,
        "latency_p50_ms": float(np.percentile([r["latency_ms"] for r in logs], 50)),
        "latency_p95_ms": float(np.percentile([r["latency_ms"] for r in logs], 95)),
        "deadline_misses": sum(r["late"] for r in logs),
        "switches": sum(r["switched"] for r in logs),
        "action_counts": {str(i): sum(r["action"] == i for r in logs) for i in range(3)},
        "confusion": cm.tolist(),
    }
    return metrics, logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=12288)
    parser.add_argument("--seed", type=int, default=27)
    args = parser.parse_args()
    if args.output.exists() or args.steps < 512:
        raise ValueError("Use new output and at least512 PPO steps")
    data = load_dataset(args.dataset)
    audit_path = args.dataset.parent / "audit.json"
    audit = json.loads(audit_path.read_text())
    if (
        hashlib.sha256(audit_path.read_bytes()).hexdigest() != audit_path.with_suffix(".sha256").read_text().strip()
        or audit.get("status") != "passed_proxy_replay_audit"
        or audit.get("dataset_sha256") != hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        or audit.get("no_raw_sweep_split_overlap") is not True
    ):
        raise ValueError("Independent raw/input/output audit required before PPO")

    if data["limit_per_scene"] != 0:
        raise ValueError("Pilot samples cannot be presented as the full MVP training run")
    from legacy.streamlit_lab.tools.local.nuscenes_local import MINI_TRAIN, MINI_VAL, NuScenesMini
    from src.config import get_settings

    dataset_index = NuScenesMini(str(get_settings().nusc_root))
    expected_scenes = set(MINI_TRAIN + MINI_VAL)
    if {episode["scene"] for episode in data["episodes"]} != expected_scenes:
        raise ValueError("Full10scene dataset required")
    for episode in data["episodes"]:
        expected = [token for token, _, scene in dataset_index.order if scene == episode["scene"]]
        expected_split = (
            "test"
            if episode["scene"] in MINI_VAL
            else ("train" if episode["scene"] in MINI_TRAIN[:6] else "validation")
        )
        if [step["token"] for step in episode["steps"]] != expected or episode["split"] != expected_split:
            raise ValueError("Incomplete frame matrix or changed split protocol")
    torch.set_num_threads(2)
    args.output.mkdir(parents=True)
    env = OccupancyProxyEnv(data, "train")
    model = PPO(
        "MlpPolicy",
        env,
        device="cpu",
        seed=args.seed,
        n_steps=128,
        batch_size=64,
        n_epochs=4,
        learning_rate=3e-4,
        gamma=0.95,
        ent_coef=0.01,
        policy_kwargs={"net_arch": {"pi": [64, 64], "vf": [64, 64]}},
        verbose=0,
    )
    before = policy_digest(model)
    model.save(args.output / "initial-policy")
    train_density = [s["observation"][0] for e in data["episodes"] if e["split"] == "train" for s in e["steps"]]
    threshold = float(np.median(train_density))

    class Validation(BaseCallback):
        def __init__(self):
            super().__init__()
            self.trace = []
            self.best = -float("inf")
            self.path = None

        def _on_step(self):
            return True

        def _on_rollout_end(self):
            if self.num_timesteps % 2048 and self.num_timesteps < args.steps:
                return
            metrics, _ = evaluate(data, "validation", model=model)
            self.trace.append({"steps": self.num_timesteps, "ppo_epoch_updates": model._n_updates, **metrics})
            if metrics["mean_scene_reward"] > self.best:
                self.best = metrics["mean_scene_reward"]
                self.path = args.output / f"validation-policy-{self.num_timesteps}"
                model.save(self.path)
            print(
                json.dumps({"validation_steps": self.num_timesteps, "reward": metrics["mean_scene_reward"]}), flush=True
            )

    callback = Validation()
    model.learn(total_timesteps=args.steps, callback=callback)
    after = policy_digest(model)
    if before == after or model._n_updates <= 0 or callback.path is None:
        raise RuntimeError("No verified PPO update or validation checkpoint")
    model.save(args.output / "final-policy")
    final_validation, _ = evaluate(data, "validation", model=model)
    callback.trace.append(
        {
            "steps": model.num_timesteps,
            "ppo_epoch_updates": model._n_updates,
            "after_final_update": True,
            **final_validation,
        }
    )
    if final_validation["mean_scene_reward"] > callback.best:
        callback.path = args.output / "final-policy"
        callback.best = final_validation["mean_scene_reward"]

    selected = PPO.load(callback.path, device="cpu")
    results, all_logs = {}, {}
    for name, options in {
        "fixed_full": {"fixed": 0},
        "fixed_half": {"fixed": 1},
        "fixed_quarter": {"fixed": 2},
        "rule": {"threshold": threshold},
        "ppo": {"model": selected},
    }.items():
        results[name], all_logs[name] = evaluate(data, "test", **options)
    winner = max(results, key=lambda key: results[key]["mean_scene_reward"])
    no_improvement = results["ppo"]["mean_scene_reward"] <= results["fixed_full"]["mean_scene_reward"] + 1e-6
    best_baseline = max(
        (name for name in results if name != "ppo"), key=lambda name: results[name]["mean_scene_reward"]
    )
    no_improvement_over_best = results["ppo"]["mean_scene_reward"] <= results[best_baseline]["mean_scene_reward"] + 1e-6
    report = {
        "kind": "measured_occupancy_proxy_ppo_research",
        "status": "completed",
        "algorithm": "PPO",
        "objective": "occupancy_proxy_quality_and_cpu_latency",
        "observation_abi": OBSERVATION_ABI,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "checkpoint_sha256": data["checkpoint_sha256"],
        "seed": args.seed,
        "actual_steps": model.num_timesteps,
        "ppo_epoch_updates": model._n_updates,
        "before_ppo_sha256": before,
        "after_ppo_sha256": after,
        "selected_policy": callback.path.name + ".zip",
        "rule_training_density_threshold": threshold,
        "split_scenes": {
            split: [e["scene"] for e in data["episodes"] if e["split"] == split]
            for split in ("train", "validation", "test")
        },
        "deadline_ms": data["deadline_ms"],
        "timing_scope": data["timing_scope"],
        "profiles": data["profiles"],
        "results": results,
        "validation": callback.trace,
        "highest_reward_baseline_or_policy": winner,
        "no_improvement_over_full": no_improvement,
        "best_baseline": best_baseline,
        "no_improvement_over_best_baseline": no_improvement_over_best,
        "conclusion": "PPO did not improve on full input; retain full baseline in this experiment."
        if no_improvement
        else "PPO has higher proxy reward on these two held-out scenes; not evidence of real-world reliability.",
        "limitations": data["limitations"]
        + [
            "Only two policy test scenes; no broad generalization claim",
            "Validation selects checkpoint; test is not used for further training or tuning",
            "GT proxy metrics do not certify perception safety or collision avoidance",
        ],
    }
    (args.output / "test-decisions.json").write_text(json.dumps(all_logs, indent=2))
    path = args.output / "report.json"
    path.write_text(json.dumps(report, indent=2))
    (args.output / "report.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    policy_file = args.output / (callback.path.name + ".zip")
    (args.output / "policy-seal.json").write_text(
        json.dumps(
            {
                "selected_policy": policy_file.name,
                "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "policy_sha256": hashlib.sha256(policy_file.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    print(json.dumps({"completed": str(path), "winner": winner, "no_improvement": no_improvement}), flush=True)


if __name__ == "__main__":
    main()
