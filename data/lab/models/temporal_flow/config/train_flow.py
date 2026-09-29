"""Stage G: temporal U-Net -> occupancy(t) [free/static/object], ground-velocity flow (vx,vy in E_t axes), future object occupancy at +0.5 s and +1.0 s.
Fixed a priori: 60 epochs, batch 8, AdamW lr 2e-3 one-cycle, wd 1e-4, seed 0, flip-y augmentation, last-epoch model reported.
Variants: T1 (single frame), T2, T4 (main = our_flow.pth), T4_nowarp (4 frames WITHOUT ego-motion compensation)."""
import json, os, sys, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from scipy.ndimage import binary_dilation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA, FLOWD, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
dev = 'cuda'
d = np.load(os.path.join(DATA, 'occ_dataset.npz'), allow_pickle=True); g = np.load(os.path.join(FLOWD, 'flow_dataset.npz'))
X = torch.from_numpy(np.concatenate([d['XL'], d['XR']], 1)).to(dev)                    # (N,7,200,200) half
Y = torch.from_numpy(d['Y'].astype(np.int64)).to(dev); split = d['split']
tr, va = np.where(split == 'train')[0], np.where(split == 'val')[0]
H = torch.from_numpy(g['H']).to(dev); A = torch.from_numpy(g['A']).to(dev); Bv = torch.from_numpy(g['B']).to(dev)
FLOW = torch.from_numpy(g['FLOW'].astype(np.float32)).to(dev); FV = torch.from_numpy(g['FVALID']).to(dev)
FUT = torch.stack([torch.from_numpy(g['FUT05']), torch.from_numpy(g['FUT10'])], 1).float().to(dev)       # (N,2,200,200)
AVL = torch.stack([torch.from_numpy(g['AV05']), torch.from_numpy(g['AV10'])], 1).float().to(dev)          # (N,2)
FM = np.stack([g['FM05'], g['FM10']], 1)
NC = 200; xs = -50 + (np.arange(NC) + 0.5) * 0.5
XXt, YYt = torch.meshgrid(torch.tensor(xs, dtype=torch.float32, device=dev), torch.tensor(xs, dtype=torch.float32, device=dev), indexing='ij')
EPOCHS, BS, LR = 60, 8, 2e-3


def stack_input(idx, T, warp):
    """(B, T*7, 200, 200) float: frames t-(T-1)..t, history warped into the current ego frame (nearest history frame of the scene reused when short)."""
    cur = X[idx].float(); frames = [cur]
    for k in range(T - 1):
        src = X[H[idx, k]].float()
        if warp:
            a, b = A[idx, k], Bv[idx, k]                                              # (B,2,2), (B,2)
            qx = a[:, 0, 0, None, None] * XXt + a[:, 0, 1, None, None] * YYt + b[:, 0, None, None]
            qy = a[:, 1, 0, None, None] * XXt + a[:, 1, 1, None, None] * YYt + b[:, 1, None, None]
            src = F.grid_sample(src, torch.stack([qy / 50.0, qx / 50.0], -1), mode='bilinear', padding_mode='zeros', align_corners=False)
        frames.append(src)
    return torch.cat(frames[::-1], 1)


def block(i, o):
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True), nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(True))


class UNet(nn.Module):
    def __init__(self, cin, base=32, nout=7):
        super().__init__()
        c = [base, base * 2, base * 4, base * 8]
        self.e1, self.e2, self.e3, self.e4 = block(cin, c[0]), block(c[0], c[1]), block(c[1], c[2]), block(c[2], c[3])
        self.u3, self.d3 = nn.ConvTranspose2d(c[3], c[2], 2, 2), block(c[3], c[2]); self.u2, self.d2 = nn.ConvTranspose2d(c[2], c[1], 2, 2), block(c[2], c[1])
        self.u1, self.d1 = nn.ConvTranspose2d(c[1], c[0], 2, 2), block(c[1], c[0]); self.out = nn.Conv2d(c[0], nout, 1)

    def forward(self, x):
        e1 = self.e1(x); e2 = self.e2(F.max_pool2d(e1, 2)); e3 = self.e3(F.max_pool2d(e2, 2)); e4 = self.e4(F.max_pool2d(e3, 2))
        x = self.d3(torch.cat([self.u3(e4), e3], 1)); x = self.d2(torch.cat([self.u2(x), e2], 1)); x = self.d1(torch.cat([self.u1(x), e1], 1))
        return self.out(x)


cls_freq = np.array([(Y[torch.from_numpy(tr).to(dev)] == c).float().mean().item() for c in range(3)])
wc = torch.tensor((1 / np.sqrt(cls_freq)) / (1 / np.sqrt(cls_freq)).sum() * 3, dtype=torch.float32, device=dev)
fut_pos = float(FUT[torch.from_numpy(tr).to(dev)].mean().item()); pos_w = torch.tensor(min(30.0, (1 - fut_pos) / max(fut_pos, 1e-6) ** 1), device=dev) ** 0.5


def losses(out, y, flow, fv, fut, av):
    lg = out[:, :3]; pr = F.softmax(lg, 1); oh = F.one_hot(y, 3).permute(0, 3, 1, 2).float()
    dice = 1 - ((2 * (pr * oh).sum((0, 2, 3)) + 1) / (pr.sum((0, 2, 3)) + oh.sum((0, 2, 3)) + 1))[1:].mean()
    l_occ = F.cross_entropy(lg, y, weight=wc) + dice
    m = fv.float().unsqueeze(1); l_flow = (F.smooth_l1_loss(out[:, 3:5] / 1.0, flow / 10.0, reduction='none') * m).sum() / (m.sum() * 2 + 1)
    l_fut = 0
    for j in range(2):
        pj = torch.sigmoid(out[:, 5 + j]); tj = fut[:, j]; w_ = av[:, j].view(-1, 1, 1)
        bce = (F.binary_cross_entropy_with_logits(out[:, 5 + j], tj, pos_weight=pos_w, reduction='none') * w_).sum() / (w_.sum() * NC * NC + 1)
        dj = 1 - (2 * (pj * tj * w_).sum() + 1) / ((pj * w_).sum() + (tj * w_).sum() + 1)
        l_fut = l_fut + bce + dj
    return l_occ + 2.0 * l_flow + 0.5 * l_fut, (l_occ.item(), float(l_flow), float(l_fut))


@torch.no_grad()
def predict(model, T, warp, idx):
    model.eval(); o = []
    for i in range(0, len(idx), 8):
        o.append(model(stack_input(torch.from_numpy(idx[i:i + 8]).to(dev), T, warp)).float().cpu())
    o = torch.cat(o).numpy(); o[:, 3:5] *= 10.0      # the network regresses flow / 10 (m/s)
    return o


def occ_metrics(pred, gt):
    r = {}; ious = []
    for c, nm in enumerate(('free', 'static', 'object')):
        i = ((pred == c) & (gt == c)).sum(); u = ((pred == c) | (gt == c)).sum(); ious.append(i / max(1, u)); r[f'IoU_{nm}'] = round(float(i / max(1, u)), 4)
    r['mIoU'] = round(float(np.mean(ious)), 4); po, go = pred > 0, gt > 0
    r['IoU_occupied'] = round(float((po & go).sum() / max(1, (po | go).sum())), 4)
    return r


def flow_metrics(fl, o_pred, gt_occ):
    """fl (n,2,200,200) predicted, GT from the dataset (val rows). EPE / angle / false-flow definitions follow the project's FLOW_CONTRACT."""
    gf = FLOW[va].cpu().numpy(); gv = FV[va].cpu().numpy(); sp = np.hypot(gf[:, 0], gf[:, 1]); pf = np.hypot(fl[:, 0], fl[:, 1])
    mov = gv & (sp >= 0.3); sta = gv & (sp < 0.3); epe = np.hypot(fl[:, 0] - gf[:, 0], fl[:, 1] - gf[:, 1])
    ang = np.rad2deg(np.arccos(np.clip((fl[:, 0] * gf[:, 0] + fl[:, 1] * gf[:, 1]) / np.maximum(pf * sp, 1e-6), -1, 1)))
    am = gv & (sp >= 0.5) & (pf >= 0.1)
    struct = gt_occ == 1
    return dict(EPE_moving=round(float(epe[mov].mean()), 3), EPE_moving_median=round(float(np.median(epe[mov])), 3), EPE_zero_flow_baseline=round(float(sp[mov].mean()), 3),
                angle_median_deg=round(float(np.median(ang[am])), 1) if am.any() else None, angle_coverage=round(float(am.sum() / max(1, (gv & (sp >= 0.5)).sum())), 3),
                static_object_false_flow_mean=round(float(pf[sta].mean()), 3), static_object_false_flow_p95=round(float(np.percentile(pf[sta], 95)), 3),
                static_structure_false_flow_mean=round(float(pf[struct].mean()), 3), n_moving_cells=int(mov.sum()), n_static_object_cells=int(sta.sum()))


def shift(mask, flow, h):
    out = np.zeros_like(mask); r, c = np.where(mask)
    if len(r) == 0:
        return out
    rr = np.clip(np.round(r + flow[0, r, c] * h / 0.5).astype(int), 0, NC - 1); cc = np.clip(np.round(c + flow[1, r, c] * h / 0.5).astype(int), 0, NC - 1)
    out[rr, cc] = True
    return out


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def future_metrics(out, occ_pred, fl):
    res = {}
    gt_occ = Y[va].cpu().numpy(); gf = FLOW[va].cpu().numpy(); gv = FV[va].cpu().numpy()
    for j, h in enumerate((0.5, 1.0)):
        av = AVL[va][:, j].cpu().numpy() > 0; fut = FUT[va][:, j].cpu().numpy() > 0; fm = FM[va][:, j] > 0; ids = np.where(av)[0]
        prob = 1 / (1 + np.exp(-out[:, 5 + j])); head = prob > 0.5
        pred_obj = occ_pred == 2; gt_obj = gt_occ == 2; spd = np.hypot(fl[:, 0], fl[:, 1])
        gsp = np.hypot(gf[:, 0], gf[:, 1])
        r = dict(n_samples=int(len(ids)))
        r['IoU_direct_future_head'] = round(float(np.mean([iou(head[i], fut[i]) for i in ids])), 4)
        r['IoU_persistence_predicted_objects'] = round(float(np.mean([iou(pred_obj[i], fut[i]) for i in ids])), 4)
        r['IoU_persistence_GT_objects(oracle)'] = round(float(np.mean([iou(gt_obj[i], fut[i]) for i in ids])), 4)
        r['IoU_flow_extrapolation_GT_objects+GT_flow(oracle)'] = round(float(np.mean([iou(np.where(gv[i] & (gsp[i] >= 0.3), False, gt_obj[i]) | shift(gv[i] & (gsp[i] >= 0.3), gf[i], h), fut[i]) for i in ids])), 4)
        r['IoU_flow_extrapolation_predicted'] = round(float(np.mean([iou(np.where(pred_obj[i] & (spd[i] >= 0.3), False, pred_obj[i]) | shift(pred_obj[i] & (spd[i] >= 0.3), fl[i], h), fut[i]) for i in ids])), 4)
        pm = pred_obj & (spd >= 0.3)      # moving-object footprint (project's flow-warped metric): shifted vs not shifted, against the moving GT footprint at t+h
        r['moving_IoU_shifted_by_predicted_flow'] = round(float(np.mean([iou(shift(pm[i], fl[i], h), fm[i]) for i in ids if fm[i].any()])), 4)
        r['moving_IoU_not_shifted'] = round(float(np.mean([iou(pm[i], fm[i]) for i in ids if fm[i].any()])), 4)
        r['n_samples_with_moving_objects'] = int(sum(fm[i].any() for i in ids))
        res[f'{h}s'] = r
    return res


VAR = {'T1': (1, True), 'T2': (2, True), 'T4': (4, True), 'T4_nowarp': (4, False)}
results, logs, saved = {}, {}, {}
Yva = Y[va].cpu().numpy()
for name, (T, warp) in VAR.items():
    torch.manual_seed(0); np.random.seed(0)
    model = UNet(T * 7).to(dev); npar = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4); sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=EPOCHS * int(np.ceil(len(tr) / BS)), pct_start=0.1)
    log = []; t0 = time.time()
    for ep in range(1, EPOCHS + 1):
        model.train(); perm = np.random.permutation(tr); tot = 0
        for i in range(0, len(perm), BS):
            b = torch.from_numpy(perm[i:i + BS]).to(dev); x = stack_input(b, T, warp); y = Y[b]; fl = FLOW[b]; fv = FV[b]; fut = FUT[b]; av = AVL[b]
            if np.random.rand() < 0.5:
                x = torch.flip(x, [3]); y = torch.flip(y, [2]); fl = torch.flip(fl, [3]) * torch.tensor([1., -1.], device=dev).view(1, 2, 1, 1); fv = torch.flip(fv, [2]); fut = torch.flip(fut, [3])
            out = model(x); loss, parts = losses(out.float(), y, fl, fv, fut, av)
            opt.zero_grad(); loss.backward(); opt.step(); sch.step(); tot += loss.item() * len(b)
        rec = dict(epoch=ep, train_loss=tot / len(tr))
        if ep % 10 == 0 or ep == 1:
            o = predict(model, T, warp, va); rec['val_mIoU'] = occ_metrics(o[:, :3].argmax(1), Yva)['mIoU']; rec['val_EPE_moving'] = flow_metrics(o[:, 3:5], None, Yva)['EPE_moving']
        log.append(rec)
        if ep % 20 == 0:
            print(name, rec, flush=True)
    secs = time.time() - t0
    path = os.path.join(OUT, f'our_flow_{name}.pth'); torch.save(dict(state_dict=model.state_dict(), T=T, warp=warp, variant=name, outputs='0-2 occupancy logits (free/static/object), 3-4 flow vx,vy m/s (ground velocity, ego(t) axes), 5-6 future object logits +0.5 s / +1.0 s',
                                                                        note=f'Stage G {name}: trained on nuScenes-mini TRAIN only, {EPOCHS} epochs'), path)
    o1 = predict(model, T, warp, va); ck = torch.load(path, map_location=dev); m2 = UNet(T * 7).to(dev); m2.load_state_dict(ck['state_dict']); o2 = predict(m2, T, warp, va)
    reload_ok = bool(np.allclose(o1, o2, atol=1e-4))
    occ_pred = o1[:, :3].argmax(1); fl = o1[:, 3:5]
    xb = stack_input(torch.from_numpy(va[:1]).to(dev), T, warp); model.eval()
    with torch.no_grad():
        for _ in range(10): model(xb)
        torch.cuda.synchronize(); t1 = time.time()
        for _ in range(100): model(xb)
        torch.cuda.synchronize(); lat = (time.time() - t1) / 100
    results[name] = dict(T=T, ego_motion_compensated=warp, occupancy=occ_metrics(occ_pred, Yva), flow=flow_metrics(fl, occ_pred, Yva), future=future_metrics(o1, occ_pred, fl),
                         params_M=round(npar / 1e6, 2), train_secs=round(secs), reload_identical=reload_ok, latency_ms_T4=round(lat * 1000, 2), final_train_loss=round(log[-1]['train_loss'], 4))
    logs[name] = log; saved[name] = o1.astype(np.float16)
    print(name, json.dumps(results[name])[:1400], flush=True)
json.dump(dict(results=results, logs=logs, epochs=EPOCHS, batch=BS, lr=LR, n_train=int(len(tr)), n_val=int(len(va))), open(os.path.join(OUT, 'flow_metrics.json'), 'w'), indent=2)
np.savez_compressed(os.path.join(OUT, 'flow_val_predictions.npz'), **{f'out_{k}': v for k, v in saved.items()}, gt_occ=Yva.astype(np.uint8), gt_flow=FLOW[va].cpu().numpy().astype(np.float16), gt_flow_valid=FV[va].cpu().numpy(),
                    fut05=FUT[va][:, 0].cpu().numpy() > 0, fut10=FUT[va][:, 1].cpu().numpy() > 0, av05=AVL[va][:, 0].cpu().numpy() > 0, av10=AVL[va][:, 1].cpu().numpy() > 0, token=d['token'][va], scene=d['scene'][va])
fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
for name, log in logs.items():
    ax[0].plot([r['epoch'] for r in log], [r['train_loss'] for r in log], label=name)
    e = [r for r in log if 'val_EPE_moving' in r]; ax[1].plot([r['epoch'] for r in e], [r['val_EPE_moving'] for r in e], 'o-', label=name)
ax[0].set_yscale('log'); ax[0].set_title('train loss'); ax[0].legend(); ax[1].set_title('mini VAL flow EPE on moving cells (monitoring only)'); ax[1].legend()
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'flow_training_curves.png'), dpi=100)
print('FLOW TRAIN PASS')
