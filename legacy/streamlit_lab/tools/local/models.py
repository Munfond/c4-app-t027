"""U-Net used by Stage F (occupancy, 3 outputs) and Stage G (temporal, 7 outputs). Same layers and names as the Kaggle training scripts, so the checkpoints load directly."""
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F


def block(i, o):
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True), nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True))


class UNet(nn.Module):
    def __init__(self, cin, base=32, nout=3):
        super().__init__()
        c = [base, base * 2, base * 4, base * 8]
        self.e1, self.e2, self.e3, self.e4 = block(cin, c[0]), block(c[0], c[1]), block(c[1], c[2]), block(c[2], c[3])
        self.u3, self.d3 = nn.ConvTranspose2d(c[3], c[2], 2, 2), block(c[3], c[2])
        self.u2, self.d2 = nn.ConvTranspose2d(c[2], c[1], 2, 2), block(c[2], c[1])
        self.u1, self.d1 = nn.ConvTranspose2d(c[1], c[0], 2, 2), block(c[1], c[0])
        self.out = nn.Conv2d(c[0], nout, 1)

    def forward(self, x):
        e1 = self.e1(x); e2 = self.e2(F.max_pool2d(e1, 2)); e3 = self.e3(F.max_pool2d(e2, 2)); e4 = self.e4(F.max_pool2d(e3, 2))
        x = self.d3(torch.cat([self.u3(e4), e3], 1)); x = self.d2(torch.cat([self.u2(x), e2], 1)); x = self.d1(torch.cat([self.u1(x), e1], 1))
        return self.out(x)


def load_occupancy(path):
    ck = torch.load(path, map_location='cpu', weights_only=False); m = UNet(len(ck['channels']), nout=3); m.load_state_dict(ck['state_dict']); m.eval()
    return m, ck


def load_flow(path):
    ck = torch.load(path, map_location='cpu', weights_only=False); m = UNet(ck['T'] * 7, nout=7); m.load_state_dict(ck['state_dict']); m.eval()
    return m, ck


def warp_history(x_hist, A, b):
    """x_hist (C,200,200) tensor of a history frame, A (2,2), b (2) -> the frame resampled into the CURRENT ego frame (bilinear, zero outside)."""
    xs = torch.tensor(-50 + (np.arange(200) + 0.5) * 0.5, dtype=torch.float32); XX, YY = torch.meshgrid(xs, xs, indexing='ij')
    A = torch.as_tensor(A); b = torch.as_tensor(b)
    qx = A[0, 0] * XX + A[0, 1] * YY + b[0]; qy = A[1, 0] * XX + A[1, 1] * YY + b[1]
    return F.grid_sample(x_hist[None], torch.stack([qy / 50.0, qx / 50.0], -1)[None], mode='bilinear', padding_mode='zeros', align_corners=False)[0]
