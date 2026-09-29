"""Stage F: train a small U-Net BEV occupancy network (free / static / object) from LiDAR (1 sweep) and/or radar BEV channels.
Fixed a priori: 80 epochs, batch 8, AdamW lr 2e-3 (cosine), weight decay 1e-4, seed 0, flip-y augmentation; last-epoch model is reported (no VAL-based selection)."""
import json, os, sys, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
dev = 'cuda'
d = np.load(os.path.join(DATA, 'occ_dataset.npz'))
XL, XR, Y, split = d['XL'].astype(np.float32), d['XR'].astype(np.float32), d['Y'].astype(np.int64), d['split']
tr, va = np.where(split == 'train')[0], np.where(split == 'val')[0]
CH = {'lidar_radar': list(range(7)), 'lidar': list(range(4)), 'radar': [4, 5, 6]}
X = np.concatenate([XL, XR], 1)
EPOCHS, BS, LR = 80, 8, 2e-3


def block(i, o):
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True), nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True))


class UNet(nn.Module):
    def __init__(self, cin, base=32, ncls=3):
        super().__init__()
        c = [base, base * 2, base * 4, base * 8]
        self.e1, self.e2, self.e3, self.e4 = block(cin, c[0]), block(c[0], c[1]), block(c[1], c[2]), block(c[2], c[3])
        self.u3, self.d3 = nn.ConvTranspose2d(c[3], c[2], 2, 2), block(c[3], c[2])
        self.u2, self.d2 = nn.ConvTranspose2d(c[2], c[1], 2, 2), block(c[2], c[1])
        self.u1, self.d1 = nn.ConvTranspose2d(c[1], c[0], 2, 2), block(c[1], c[0])
        self.out = nn.Conv2d(c[0], ncls, 1)

    def forward(self, x):
        e1 = self.e1(x); e2 = self.e2(F.max_pool2d(e1, 2)); e3 = self.e3(F.max_pool2d(e2, 2)); e4 = self.e4(F.max_pool2d(e3, 2))
        x = self.d3(torch.cat([self.u3(e4), e3], 1)); x = self.d2(torch.cat([self.u2(x), e2], 1)); x = self.d1(torch.cat([self.u1(x), e1], 1))
        return self.out(x)


def metrics(pred, gt):
    """pred, gt: (n,200,200) int. strict per-cell IoU + 1-cell-tolerant binary occupied precision/recall."""
    out = {}
    ious = []
    for c, nm in enumerate(('free', 'static', 'object')):
        i = ((pred == c) & (gt == c)).sum(); u = ((pred == c) | (gt == c)).sum(); ious.append(i / max(1, u)); out[f'IoU_{nm}'] = round(float(i / max(1, u)), 4)
    out['mIoU'] = round(float(np.mean(ious)), 4); out['mIoU_occupied_classes'] = round(float(np.mean(ious[1:])), 4)
    po, go = pred > 0, gt > 0; i = (po & go).sum(); u = (po | go).sum()
    out['IoU_occupied(static+object)'] = round(float(i / max(1, u)), 4)
    out['occupied_precision'] = round(float(i / max(1, po.sum())), 4); out['occupied_recall'] = round(float(i / max(1, go.sum())), 4)
    from scipy.ndimage import binary_dilation
    k = np.ones((1, 3, 3), bool)
    out['occupied_precision_tol1'] = round(float((po & binary_dilation(go, k)).sum() / max(1, po.sum())), 4); out['occupied_recall_tol1'] = round(float((go & binary_dilation(po, k)).sum() / max(1, go.sum())), 4)
    o_p, o_g = pred == 2, gt == 2
    out['object_precision'] = round(float((o_p & o_g).sum() / max(1, o_p.sum())), 4); out['object_recall'] = round(float((o_p & o_g).sum() / max(1, o_g.sum())), 4)
    return out


@torch.no_grad()
def predict(model, x):
    model.eval(); out = []
    for i in range(0, len(x), 8):
        out.append(model(torch.from_numpy(x[i:i + 8]).to(dev)).argmax(1).cpu().numpy())
    return np.concatenate(out).astype(np.uint8)


freq = np.array([(Y[tr] == c).mean() for c in range(3)]); w = torch.tensor((1 / np.sqrt(freq)) / (1 / np.sqrt(freq)).sum() * 3, dtype=torch.float32, device=dev)
print('class freq', freq.round(4), 'weights', w.cpu().numpy().round(2))
results, logs, preds = {}, {}, {}
Yva = Y[va]
# ---- baselines on the same VAL grids -------------------------------------------------------------------------------------
rule = (XL[va][:, 0] > 0).astype(np.int64)   # any obstacle-height LiDAR point in the keyframe -> occupied
results['baseline_rule_single_sweep_obstacle_height'] = {k: v for k, v in metrics(rule, Yva).items() if k.startswith(('IoU_occupied', 'occupied'))}
print('rule baseline', results['baseline_rule_single_sweep_obstacle_height'])
for name, ch in CH.items():
    torch.manual_seed(0); np.random.seed(0)
    model = UNet(len(ch)).to(dev); nparam = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4); steps = EPOCHS * int(np.ceil(len(tr) / BS)); sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=steps, pct_start=0.1)
    Xt = X[:, ch]; log = []
    t0 = time.time()
    for ep in range(1, EPOCHS + 1):
        model.train(); perm = np.random.permutation(tr); tot = 0
        for i in range(0, len(perm), BS):
            b = perm[i:i + BS]; x = torch.from_numpy(Xt[b]).to(dev); y = torch.from_numpy(Y[b]).to(dev)
            if np.random.rand() < 0.5:
                x = torch.flip(x, [3]); y = torch.flip(y, [2])
            lg = model(x); pr = F.softmax(lg, 1); oh = F.one_hot(y, 3).permute(0, 3, 1, 2).float()
            dice = 1 - ((2 * (pr * oh).sum((0, 2, 3)) + 1) / (pr.sum((0, 2, 3)) + oh.sum((0, 2, 3)) + 1))[1:].mean()
            loss = F.cross_entropy(lg, y, weight=w) + dice
            opt.zero_grad(); loss.backward(); opt.step(); sch.step(); tot += loss.item() * len(b)
        rec = dict(epoch=ep, train_loss=tot / len(tr))
        if ep % 10 == 0 or ep == 1:
            m = metrics(predict(model, Xt[va]), Yva); rec.update(val_mIoU=m['mIoU'], val_IoU_occupied=m['IoU_occupied(static+object)'])
        log.append(rec)
        if ep % 20 == 0:
            print(name, rec, flush=True)
    secs = time.time() - t0
    torch.save(dict(state_dict=model.state_dict(), channels=ch, variant=name, note=f'Stage F {name}: U-Net BEV occupancy trained on nuScenes-mini TRAIN only, {EPOCHS} epochs', classes=['free', 'static', 'object']), os.path.join(OUT, f'our_occupancy_{name}.pth'))
    # reload test: fresh model from the file must reproduce the predictions exactly
    p1 = predict(model, Xt[va]); ck = torch.load(os.path.join(OUT, f'our_occupancy_{name}.pth'), map_location=dev)
    m2 = UNet(len(ch)).to(dev); m2.load_state_dict(ck['state_dict']); p2 = predict(m2, Xt[va]); reload_ok = bool((p1 == p2).all())
    # latency
    xb = torch.from_numpy(Xt[va[:1]]).to(dev); model.eval()
    with torch.no_grad():
        for _ in range(10): model(xb)
        torch.cuda.synchronize(); t1 = time.time()
        for _ in range(100): model(xb)
        torch.cuda.synchronize(); lat = (time.time() - t1) / 100
    results[name] = dict(metrics(p1, Yva), params_M=round(nparam / 1e6, 2), train_secs=round(secs), reload_identical=reload_ok, latency_ms_T4=round(lat * 1000, 2),
                         final_train_loss=round(log[-1]['train_loss'], 4), peak_mem_MB=round(torch.cuda.max_memory_allocated() / 1e6))
    logs[name] = log; preds[name] = p1
    print(name, results[name], flush=True)
json.dump(dict(results=results, logs=logs, class_freq_train=freq.tolist(), epochs=EPOCHS, batch=BS, lr=LR, n_train=int(len(tr)), n_val=int(len(va))), open(os.path.join(OUT, 'occupancy_metrics.json'), 'w'), indent=2)
np.savez_compressed(os.path.join(OUT, 'occ_val_predictions.npz'), **{f'pred_{k}': v for k, v in preds.items()}, gt=Yva.astype(np.uint8), XL=XL[va].astype(np.float16), XR=XR[va].astype(np.float16), token=d['token'][va], scene=d['scene'][va])
fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
for name, log in logs.items():
    ax[0].plot([r['epoch'] for r in log], [r['train_loss'] for r in log], label=name)
    e = [r for r in log if 'val_mIoU' in r]; ax[1].plot([r['epoch'] for r in e], [r['val_mIoU'] for r in e], 'o-', label=name)
ax[0].set_title('train loss'); ax[0].set_yscale('log'); ax[0].legend(); ax[1].set_title('mini VAL mIoU (monitoring only, no selection)'); ax[1].legend(); ax[0].set_xlabel('epoch'); ax[1].set_xlabel('epoch')
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'occupancy_training_curves.png'), dpi=100)
print('OCCUPANCY TRAIN PASS')
