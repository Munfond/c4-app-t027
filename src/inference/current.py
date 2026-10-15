"""Load verified project checkpoints and execute them on common BEV frame records."""

import time

import numpy as np

from src.config import get_settings
from src.services.experiment_registry import MODELS, checkpoint_path, verified_hash


class CurrentCheckpoint:
    def __init__(self, model_id, device="cpu"):
        import torch

        from legacy.streamlit_lab.tools.local.models import UNet

        self.model_id = model_id
        _, self.task, self.channels, self.history, self.warp = MODELS[model_id]
        self.digest = verified_hash(model_id)
        self.torch = torch
        self.device = device
        self.timing = []
        if device == "cpu":
            torch.set_num_threads(get_settings().experiment_cpu_threads)
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable")
        ck = torch.load(checkpoint_path(model_id), map_location="cpu", weights_only=True)
        if self.task == "occupancy" and list(ck["channels"]) != self.channels:
            raise ValueError("Checkpoint channels do not match registry")
        if self.task == "flow" and (ck["T"] != self.history or bool(ck["warp"]) != self.warp):
            raise ValueError("Checkpoint history/warp do not match registry")
        cin = len(self.channels) if self.task == "occupancy" else self.history * 7
        self.model = UNet(cin, nout=3 if self.task == "occupancy" else 7)
        self.model.load_state_dict(ck["state_dict"], strict=True)
        self.model.to(device).eval()
        self.warmed = False

    def predict(self, frames, index):
        from legacy.streamlit_lab.tools.local.models import warp_history

        torch = self.torch
        current = frames[index]
        if self.task == "occupancy":
            x = torch.from_numpy(current["x"][self.channels]).float()
        else:
            stack = [torch.from_numpy(current["x"]).float()]
            for k in range(1, self.history):
                previous = frames[max(0, index - k)]
                xprev = torch.from_numpy(previous["x"]).float()
                if self.warp:
                    rot = previous["rotation"].T @ current["rotation"]
                    offset = previous["rotation"].T @ (current["translation"] - previous["translation"])
                    xprev = warp_history(xprev, rot[:2, :2], offset[:2])
                stack.append(xprev)
            x = torch.cat(stack[::-1], 0)
        x = x[None].to(self.device)
        with torch.inference_mode():
            if not self.warmed:
                self.model(x)
                self.warmed = True
            if self.device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
            output = self.model(x)
            if self.device == "cuda":
                torch.cuda.synchronize()
            self.timing.append((time.perf_counter() - start) * 1000)
            result = output[0].cpu().numpy()
        return {
            "occupancy": result[:3].argmax(0).astype(np.uint8),
            "flow": (result[3:5] * 10).astype(np.float32) if self.task == "flow" else None,
        }
