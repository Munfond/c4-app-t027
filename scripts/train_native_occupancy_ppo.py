"""Execute the sealed native research protocol; no online control or deployment claim."""

import argparse
import hashlib
import json
import signal
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO

from scripts.build_native_occupancy_replay import write_sealed
from scripts.train_occupancy_proxy_ppo import policy_digest
from src.active_sensing.native_occupancy import BASELINE, NativeOccupancyEnv, load_dataset, quality, read_sealed


def evaluate(data, split, *, model=None, fixed=None):
    env = NativeOccupancyEnv(data, split)
    logs, rewards, bootstrap = [], [], []
    for episode in range(len(env.episodes)):
        obs, boot = env.reset(options={"episode": episode})
        bootstrap.append({"episode": env.episode["id"], **boot})
        values, done = [], False
        while not done:
            action = int(model.predict(obs, deterministic=True)[0]) if model is not None else fixed
            obs, reward, done, _, info = env.step(action)
            values.append(reward)
            logs.append({"episode": env.episode["id"], "action": action, "reward": reward, **info})
        rewards.append(float(np.mean(values)))
    cm = np.asarray([r["confusion"] for r in logs]).sum(axis=0)
    return {
        "mean_episode_reward": float(np.mean(rewards)),
        **quality(cm, max_cells=len(logs) * 40000),
        "confusion": cm.tolist(),
        "decisions": len(logs),
        "episodes": len(rewards),
        "bootstrap": bootstrap,
        "latency_p50_ms": float(np.percentile([r["latency_ms"] for r in logs], 50)),
        "latency_p95_ms": float(np.percentile([r["latency_ms"] for r in logs], 95)),
        "switches": sum(r["switched"] for r in logs),
        "late": sum(r["late"] for r in logs),
        "action_counts": {str(a): sum(r["action"] == a for r in logs) for a in range(12)},
    }, logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use new output; preserve earlier evidence")
    plan, plan_hash = read_sealed(args.plan)
    # Fixed architecture/hyperparameters are not command-line knobs: changing the protocol requires new data/splits.
    if (
        plan.get("kind") != "native_occupancy_research_training_plan_v1"
        or plan["steps"] != 8192
        or plan["validation_interval"] != 1024
        or plan["seed"] != 27
        or plan["deployment_ready"] is not False
    ):
        raise ValueError("Wrong preregistered native training protocol")
    data = load_dataset(args.dataset)
    dataset_sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    audit, audit_sha = read_sealed(args.dataset.parent / "audit.json")
    if (
        audit.get("status") != "passed_research_audit"
        or audit.get("research_training_admitted") is not True
        or audit.get("dataset_sha256") != dataset_sha
        or audit.get("deployment_ready") is not False
        or plan["capture_plan_sha256"] != data["capture_plan_sha256"]
        or plan["reward"] != data["reward"]
        or plan["observation_abi"] != data["observation_abi"]
    ):
        raise ValueError("Independent native replay audit required before PPO")
    args.output.mkdir(parents=True)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        write_sealed(args.output / "training-plan.json", plan)
        torch.set_num_threads(2)
        model = PPO(
            "MlpPolicy",
            NativeOccupancyEnv(data),
            device="cpu",
            seed=plan["seed"],
            n_steps=plan["n_steps"],
            batch_size=plan["batch_size"],
            n_epochs=plan["n_epochs"],
            learning_rate=plan["learning_rate"],
            gamma=plan["gamma"],
            ent_coef=plan["ent_coef"],
            policy_kwargs={"net_arch": {"pi": plan["net_arch"], "vf": plan["net_arch"]}},
            verbose=0,
        )
        initial = policy_digest(model)
        model.save(args.output / "initial-policy")
        trace, best, selected_path = [], -float("inf"), None
        for stage in range(plan["steps"] // plan["validation_interval"]):
            model.learn(total_timesteps=plan["validation_interval"], reset_num_timesteps=False)
            metrics, _ = evaluate(data, "validation", model=model)
            row = {"actual_steps": model.num_timesteps, "ppo_epoch_updates": model._n_updates, **metrics}
            trace.append(row)
            if metrics["mean_episode_reward"] > best:
                best = metrics["mean_episode_reward"]
                selected_path = args.output / f"validation-policy-{model.num_timesteps}"
                model.save(selected_path)
            write_sealed(
                args.output / "training-progress.json",
                {"status": "training", "validation": trace, "test_evaluated": False},
            )
            print(
                json.dumps(
                    {
                        "actual_steps": model.num_timesteps,
                        "ppo_epoch_updates": model._n_updates,
                        "validation_reward": best,
                    }
                ),
                flush=True,
            )
        final = policy_digest(model)
        if final == initial or model._n_updates <= 0 or selected_path is None:
            raise ValueError("No verified PPO optimizer updates")
        model.save(args.output / "final-policy")
        selected = PPO.load(selected_path, device="cpu")
        # Policy selection is complete before any test baseline or PPO score is inspected.
        results, logs = {}, {}
        for action in range(12):
            name = f"fixed_{action:02d}"
            results[name], logs[name] = evaluate(data, "test", fixed=action)
        results["ppo"], logs["ppo"] = evaluate(data, "test", model=selected)
        baseline = results[f"fixed_{BASELINE:02d}"]["mean_episode_reward"]
        best_fixed = max((k for k in results if k != "ppo"), key=lambda k: results[k]["mean_episode_reward"])
        no_improvement = results["ppo"]["mean_episode_reward"] <= baseline + 1e-6
        selected_sha = hashlib.sha256(selected_path.with_suffix(".zip").read_bytes()).hexdigest()
        report = {
            "kind": "native_occupancy_ppo_research_v1",
            "status": "completed",
            "algorithm": "PPO",
            "dataset_sha256": dataset_sha,
            "audit_sha256": audit_sha,
            "training_plan_sha256": plan_hash,
            "observation_abi": data["observation_abi"],
            "checkpoint_sha256": data["checkpoint_sha256"],
            "adapter": data["adapter"],
            "actual_steps": model.num_timesteps,
            "ppo_epoch_updates": model._n_updates,
            "before_ppo_sha256": initial,
            "after_ppo_sha256": final,
            "selected_policy": selected_path.name + ".zip",
            "selected_policy_sha256": selected_sha,
            "selected_policy_trained_steps": int(selected_path.name.rsplit("-", 1)[1]),
            "profiles": data["profiles"],
            "baseline_action": BASELINE,
            "validation": trace,
            "test_results": results,
            "no_improvement_over_full": no_improvement,
            "best_test_fixed_for_comparison_only": best_fixed,
            "no_improvement_over_best_fixed": results["ppo"]["mean_episode_reward"]
            <= results[best_fixed]["mean_episode_reward"] + 1e-6,
            "deployment_ready": False,
            "limitations": data["limits"],
            "conclusion": "No better policy than full baseline on this research test; retain full configuration."
            if no_improvement
            else "Higher replay reward on one held-out route only; require additional unseen routes before any deployment.",
        }
        write_sealed(args.output / "report.json", report)
        write_sealed(args.output / "test-traces.json", logs)
        write_sealed(
            args.output / "training-progress.json", {"status": "completed", "validation": trace, "test_evaluated": True}
        )
        print(
            json.dumps(
                {
                    "status": "completed",
                    "actual_steps": model.num_timesteps,
                    "no_improvement_over_full": no_improvement,
                    "deployment_ready": False,
                }
            )
        )
    except BaseException as exc:
        progress_path = args.output / "training-progress.json"
        progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
        progress.update(status="incomplete", error_type=type(exc).__name__, test_evaluated=False)
        write_sealed(progress_path, progress)
        raise


if __name__ == "__main__":
    main()
