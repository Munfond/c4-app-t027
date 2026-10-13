"""Optional non-recurrent masked PPO with a rollout-fixed Lagrange penalty.

This implementation targets mean per-window constraint cost, not a certified
chance constraint. Asymmetric critics and stateful perception are deferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.active_sensing.replay import Replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=27)
    parser.add_argument("--bc-steps", type=int, default=200)
    parser.add_argument("--allow-synthetic", action="store_true", help="Software smoke only; never benchmark evidence")
    args = parser.parse_args()
    if args.steps <= 0 or args.bc_steps < 0:
        parser.error("steps must be positive and bc-steps nonnegative")
    replay = Replay.load(args.replay, allow_synthetic=args.allow_synthetic)
    if replay.objective != "quality_latency":
        raise ValueError("MVP training requires constraints.objective=quality_latency; GPU objectives are archived only")
    if args.output.exists():
        raise ValueError("Preserve prior training output; choose a new directory")
    # Heavy optional imports are deliberately isolated from the API and core.
    import numpy as np
    import torch
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.callbacks import BaseCallback

    from src.active_sensing.gym_env import ReplayEnv

    env = ReplayEnv(replay, split="train")
    model = MaskablePPO(
        "MlpPolicy", env, device="cpu", seed=args.seed,
        learning_rate=3e-4, gamma=0.95, gae_lambda=0.95, clip_range=0.2,
        n_steps=256, batch_size=64, n_epochs=10, ent_coef=0.01,
        policy_kwargs={"net_arch": {"pi": [128, 128], "vf": [128, 128]}},
        verbose=1,
    )

    # Behavior cloning uses the same observable baseline; no GT-derived teacher action.
    observation, _ = env.reset(seed=args.seed)
    model.policy.set_training_mode(True)
    for _ in range(args.bc_steps):
        teacher = replay.rule.select(replay.observation())
        masks = env.action_masks()
        index = next(i for i, p in enumerate(replay.profiles) if p.id == teacher)
        if not masks[index]:
            index = int(np.flatnonzero(masks)[0])
        tensor, _ = model.policy.obs_to_tensor(observation[None])
        _, log_prob, _ = model.policy.evaluate_actions(
            tensor, torch.as_tensor([index], dtype=torch.long, device=model.device),
            action_masks=masks[None],
        )
        loss = -log_prob.mean()
        model.policy.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.policy.parameters(), 0.5)
        model.policy.optimizer.step()
        observation, _, done, _, _ = env.step(index)
        if done:
            observation, _ = env.reset()

    class DualUpdate(BaseCallback):
        def __init__(self):
            super().__init__()
            self.costs = []
            self.trace = []

        def _on_rollout_start(self):
            self.costs = []

        def _on_step(self):
            self.costs.extend(
                info["metrics"]["constraint_cost"] for info in self.locals["infos"]
                if "metrics" in info
            )
            return True

        def _on_rollout_end(self):
            if not self.costs:
                raise RuntimeError("No measured constraint costs")
            rate = float(np.mean(self.costs))
            # Environment shaped each collected reward with one fixed beta.
            # Update beta for NEXT rollout; never rewrite rewards after GAE.
            env.set_multiplier(env.multiplier + 0.01 * (rate - replay.constraints.miss_rate_limit))
            self.trace.append({
                "steps": self.num_timesteps, "cost_rate": rate, "next_beta": env.multiplier,
            })
            self.logger.record("constraint/mean_window_cost", rate)
            self.logger.record("constraint/next_beta", env.multiplier)

    def digest():
        h = hashlib.sha256()
        for name, tensor in sorted(model.policy.state_dict().items()):
            h.update(name.encode())
            h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()

    before = digest()
    before_updates = model._n_updates
    args.output.mkdir(parents=True)
    model.save(args.output / "policy-before-ppo")
    callback = DualUpdate()
    model.learn(total_timesteps=args.steps, callback=callback)
    after = digest()
    epochs = model._n_updates - before_updates
    if epochs <= 0 or before == after:
        raise RuntimeError("PPO policy state did not update; preserve output for investigation")
    model.save(args.output / "policy")
    (args.output / "training.json").write_text(json.dumps({
        "provenance": replay.provenance, "seed": args.seed,
        "objective": replay.objective,
        "observation_abi": "quality-latency-v1" if replay.objective == "quality_latency" else "legacy-gpu-quality",
        "algorithm": "MaskablePPO", "bc_steps": args.bc_steps,
        "ppo_epoch_updates": epochs, "before_ppo_sha256": before, "after_ppo_sha256": after,
        "actual_steps": model.num_timesteps, "profiles": [p.id for p in replay.profiles],
        "final_multiplier": env.multiplier, "dual_updates": callback.trace,
        "validated_on_test": False,
        "notice": "Training completion does not establish reliability or GPU savings.",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
