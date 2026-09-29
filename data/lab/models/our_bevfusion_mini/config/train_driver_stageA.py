"""Smoke-train -> verify -> full-train -> evaluate -> export driver for BEVFusion on nuScenes-mini (runs inside the frozen env)."""
import glob, json, os, re, shutil, subprocess, sys, time
import numpy as np

W = os.environ.get('W', '/tmp/l3')
PY = os.environ['PY']
OUT = os.environ.get('OUT', '/kaggle/working/outputs')
MMD = f'{W}/mmdetection3d'
CFG = os.environ.get('OUR_CFG', 'projects/BEVFusion/configs/our_lidar_mini.py')
NAME = os.environ.get('OUR_NAME', 'our_lidar_mini')
BUDGET_S = float(os.environ.get('OUR_BUDGET_S', 11520))
STAGE_DIR = os.path.join(OUT, NAME)
KEY_NDS = 'NuScenes metric/pred_instances_3d_NuScenes/NDS'
KEY_MAP = 'NuScenes metric/pred_instances_3d_NuScenes/mAP'
os.makedirs(f'{W}/logs', exist_ok=True)
os.makedirs(STAGE_DIR, exist_ok=True)


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def tail_progress(path):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 6000))
            txt = f.read().decode('utf-8', 'replace')
        lines = [l for l in txt.splitlines() if 'Epoch(' in l or 'Traceback' in l or 'Error' in l]
        if lines:
            print('   ..', lines[-1][-260:], flush=True)
    except Exception:
        pass


def run(cmd, extra_env, logfile, every=300):
    env = dict(os.environ)
    env.update({k: str(v) for k, v in extra_env.items()})
    env['PYTHONPATH'] = MMD + ':' + env.get('PYTHONPATH', '')
    with open(logfile, 'w') as f:
        p = subprocess.Popen(cmd, cwd=MMD, env=env, stdout=f, stderr=subprocess.STDOUT)
        last = 0
        while p.poll() is None:
            time.sleep(10)
            if time.time() - last > every:
                last = time.time(); tail_progress(logfile)
    tail_progress(logfile)
    return p.returncode


def train(tag, epochs, lr, accum, val_int, amp, extra=None):
    wd = f'{W}/work_dirs/{tag}'
    shutil.rmtree(wd, ignore_errors=True)
    cmd = [PY, '-W', 'ignore', 'tools/train.py', CFG, '--work-dir', wd] + (['--amp'] if amp else [])
    env = dict(OUR_EPOCHS=epochs, OUR_LR=lr, OUR_ACCUM=accum, OUR_VAL_INT=val_int)
    env.update(extra or {})
    lf = f'{W}/logs/train_{tag}.log'
    t0 = time.time()
    rc = run(cmd, env, lf)
    return dict(rc=rc, wd=wd, log=lf, secs=time.time() - t0, tag=tag)


def load_scalars(wd):
    fs = sorted(glob.glob(f'{wd}/*/vis_data/scalars.json'))
    if not fs:
        return None, []
    recs = []
    for l in open(fs[-1]):
        l = l.strip()
        if l:
            try:
                recs.append(json.loads(l))
            except Exception:
                pass
    return fs[-1], recs


def summarize(wd, log_path, epochs):
    sp, recs = load_scalars(wd)
    tr = [r for r in recs if 'loss' in r]
    val = [r for r in recs if KEY_NDS in r]
    txt = open(log_path, errors='replace').read()
    m = re.findall(r'Epoch\(train\)\s+\[1\]\[\s*\d+/(\d+)\]', txt)
    iters_per_epoch = int(m[-1]) if m else None
    rep = dict(n_train_records=len(tr), n_val_records=len(val), iters_per_epoch=iters_per_epoch,
               oom=('out of memory' in txt.lower()), scalars=sp)
    if not tr:
        rep['ok'] = False; rep['why'] = 'no train records'; return rep, tr, val
    loss = np.array([r['loss'] for r in tr], float)
    gn = np.array([r.get('grad_norm', 0.0) for r in tr], float)
    q = max(1, len(loss) // 4)
    rep.update(loss_finite=bool(np.isfinite(loss).all()), gradnorm_nonfinite_frac=float(np.mean(~np.isfinite(gn))),
               loss_first_quarter=float(np.nanmean(loss[:q])), loss_last_quarter=float(np.nanmean(loss[-q:])),
               sec_per_iter=float(np.median([r['time'] for r in tr if 'time' in r])),
               max_mem_mb=float(max([r.get('memory', 0) for r in tr])), last_lr=float(tr[-1].get('lr', 0)))
    ck = os.path.join(wd, f'epoch_{epochs}.pth')
    rep['ckpt_exists'] = os.path.exists(ck)
    rep['ok'] = bool(rep['loss_finite'] and rep['gradnorm_nonfinite_frac'] < 0.2 and rep['ckpt_exists']
                     and rep['loss_last_quarter'] < rep['loss_first_quarter'])
    return rep, tr, val


def evaluate(ckpt, tag):
    exp = f'{W}/exports/{tag}'
    shutil.rmtree(exp, ignore_errors=True)
    lf = f'{W}/logs/eval_{tag}.log'
    cmd = [PY, '-W', 'ignore', 'tools/test.py', CFG, ckpt, '--work-dir', f'{W}/work_dirs/eval_{tag}',
           '--cfg-options', f'test_evaluator.jsonfile_prefix={exp}']
    rc = run(cmd, {}, lf, every=120)
    txt = open(lf, errors='replace').read()
    mism = ('size mismatch' in txt) or ('missing keys in source state_dict' in txt) or ('unexpected key in source state_dict' in txt)
    ms = glob.glob(f'{exp}/**/metrics_summary.json', recursive=True)
    res = glob.glob(f'{exp}/**/results_nusc.json', recursive=True)
    out = dict(tag=tag, ckpt=os.path.basename(ckpt), rc=rc, load_mismatch=mism)
    if ms:
        m = json.load(open(ms[0]))
        out.update(mAP=m['mean_ap'], NDS=m['nd_score'], mATE=m['tp_errors']['trans_err'], mASE=m['tp_errors']['scale_err'],
                   mAOE=m['tp_errors']['orient_err'], mAVE=m['tp_errors']['vel_err'], mAAE=m['tp_errors']['attr_err'],
                   per_class_AP_2m={k: v for k, v in m['mean_dist_aps'].items()})
        out['results_json'] = res[0] if res else None
    out['ok'] = bool(ms) and rc == 0 and not mism
    return out


def strip(ckpt, dst, note):
    import torch
    c = torch.load(ckpt, map_location='cpu')
    keep = dict(state_dict=c['state_dict'], meta=c.get('meta', {}))
    keep['meta']['our_note'] = note
    torch.save(keep, dst)
    return os.path.getsize(dst) / 1e6


def curves(tr, val, outdir, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(outdir, exist_ok=True)
    it = np.arange(len(tr)) * 1.0
    loss = np.array([r['loss'] for r in tr])
    k = 10
    sm = np.convolve(loss, np.ones(k) / k, mode='valid') if len(loss) > k else loss
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.5))
    ax[0].plot(it, loss, alpha=.3, label='loss (logged every 20 it)'); ax[0].plot(np.arange(len(sm)) + k / 2, sm, label='moving avg')
    ax[0].set_title(title + ' | total loss'); ax[0].set_xlabel('log step'); ax[0].legend(); ax[0].set_yscale('log')
    for key in ('loss_heatmap', 'loss_cls', 'loss_bbox'):
        v = [r.get(key) for r in tr if key in r]
        if v:
            ax[1].plot(v, label=key, alpha=.8)
    lay = [k2 for k2 in tr[0].keys() if k2.endswith('_loss_cls') or k2.endswith('loss_cls')]
    ax[1].set_title('loss components'); ax[1].legend(); ax[1].set_yscale('log')
    fig.tight_layout(); fig.savefig(f'{outdir}/loss.png', dpi=100); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4)); ax.plot([r.get('lr', 0) for r in tr]); ax.set_title('learning rate'); ax.set_xlabel('log step')
    fig.tight_layout(); fig.savefig(f'{outdir}/lr.png', dpi=100); plt.close(fig)
    if val:
        fig, ax = plt.subplots(figsize=(7, 4))
        st = [r.get('step', i) for i, r in enumerate(val)]
        ax.plot(st, [r[KEY_NDS] for r in val], 'o-', label='NDS'); ax.plot(st, [r[KEY_MAP] for r in val], 's-', label='mAP')
        ax.set_title('mini VAL metrics vs epoch'); ax.set_xlabel('epoch'); ax.legend(); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(f'{outdir}/val_metrics.png', dpi=100); plt.close(fig)


DRYRUN_SCRIPT = r"""
import sys, os, importlib, numpy as np
sys.path.insert(0, os.getcwd())
from mmengine import Config
from mmdet3d.utils import register_all_modules
register_all_modules(init_default_scope=True)
from mmdet3d.registry import DATASETS
cfg = Config.fromfile(os.environ['OUR_CFG'])
for m in cfg.get('custom_imports', {}).get('imports', []):
    importlib.import_module(m)
ds = DATASETS.build(cfg.train_dataloader.dataset)
n = len(ds)
print('train dataset len (CBGS-resampled):', n)
for i in np.linspace(0, n - 1, 24).astype(int):
    it = ds[int(i)]
    p = it['inputs']['points']
    g = it['data_samples'].gt_instances_3d
    im = it['inputs'].get('img')
    print(int(i), 'points', tuple(p.shape), 'gt boxes', len(g.labels_3d), 'img', None if im is None else tuple(im.shape), flush=True)
print('DRYRUN PASS')
"""


def dryrun():
    env = dict(os.environ)
    env['PYTHONPATH'] = MMD + ':' + env.get('PYTHONPATH', '')
    env['OUR_CFG'] = CFG
    r = subprocess.run([PY, '-W', 'ignore', '-c', DRYRUN_SCRIPT], cwd=MMD, env=env, capture_output=True, text=True)
    out = (r.stdout or '') + (r.stderr or '')
    print(out[-3500:], flush=True)
    if 'DRYRUN PASS' not in out:
        log('DRYRUN FAIL (train data pipeline broken; hyper-parameter retries would be pointless)')
        sys.exit(4)


def main():
    smoke_only = os.environ.get('OUR_SMOKE_ONLY') == '1'
    attempts = [dict(amp=True, lr=3e-5, accum=4, extra={}),
                dict(amp=True, lr=3e-5, accum=4, extra={'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True', 'OUR_WORKERS': 2}),
                dict(amp=True, lr=1.5e-5, accum=4, extra={'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'}),
                dict(amp=False, lr=1.5e-5, accum=4, extra={'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'})]
    chosen, smoke_reports = None, []
    dryrun()
    for i, a in enumerate(attempts):
        log(f'=== SMOKE attempt {i}: {a}')
        r = train(f'smoke{i}', 2, a['lr'], a['accum'], 1, a['amp'], a['extra'])
        rep, tr, val = summarize(r['wd'], r['log'], 2)
        rep.update(attempt=i, params={k: v for k, v in a.items()}, rc=r['rc'], secs=r['secs'])
        if rep.get('ckpt_exists'):
            ev = evaluate(os.path.join(r['wd'], 'epoch_2.pth'), f'smoke{i}')
            rep['reload_eval'] = {k: v for k, v in ev.items() if k != 'per_class_AP_2m'}
            rep['ok'] = bool(rep['ok'] and ev['ok'])
        log('smoke report:', json.dumps({k: v for k, v in rep.items() if k not in ('params',)}, default=str)[:1500])
        smoke_reports.append(rep)
        if rep['ok']:
            chosen = (a, rep); break
        log('smoke attempt failed; tail of log:'); print(open(r['log'], errors='replace').read()[-2500:])
        if rep.get('why') == 'no train records' and not rep['oom']:
            log('non-OOM crash: retrying with other hyper-parameters is pointless -> stop'); break
    os.makedirs(f'{STAGE_DIR}/training_logs', exist_ok=True)
    json.dump(smoke_reports, open(f'{STAGE_DIR}/training_logs/smoke_report.json', 'w'), indent=2, default=str)
    if not chosen:
        log('SMOKE FAIL'); sys.exit(2)
    a, rep = chosen
    log('SMOKE PASS with', a)
    print('SMOKE PASS')
    if smoke_only:
        return
    ipe, spi = rep['iters_per_epoch'], rep['sec_per_iter']
    epoch_s = (ipe * spi) if (ipe and spi) else 600.0
    val_int = 2
    E = int(np.clip(BUDGET_S / (epoch_s * 1.08), 12, 60))
    log(f'iters/epoch={ipe} sec/iter={spi:.3f} epoch~{epoch_s / 60:.1f} min -> full schedule EPOCHS={E}, val_interval={val_int}')
    r = train('full', E, a['lr'], a['accum'], val_int, a['amp'], a['extra'])
    rep_full, tr, val = summarize(r['wd'], r['log'], E)
    rep_full.update(rc=r['rc'], secs=r['secs'], epochs=E, params=a)
    json.dump(rep_full, open(f'{STAGE_DIR}/training_logs/full_train_report.json', 'w'), indent=2, default=str)
    if not rep_full.get('ckpt_exists'):
        print(open(r['log'], errors='replace').read()[-3000:]); log('FULL TRAIN FAIL'); sys.exit(3)
    finish(r['wd'], r['log'], E, tr, val, rep_full)


def finish(wd, logf, E, tr, val, rep_full):
    os.makedirs(f'{STAGE_DIR}/training_logs', exist_ok=True)
    shutil.copy(logf, f'{STAGE_DIR}/training_logs/train_full.log')
    sp, _ = load_scalars(wd)
    if sp:
        shutil.copy(sp, f'{STAGE_DIR}/training_logs/scalars.json')
    curves(tr, val, f'{STAGE_DIR}/training_curves', NAME)
    last = os.path.join(wd, f'epoch_{E}.pth')
    note = f'{NAME}: trained from scratch on nuScenes-mini TRAIN (no official checkpoint), epochs={E}'
    mb = strip(last, f'{STAGE_DIR}/{NAME}.pth', note)
    log(f'{NAME}.pth written ({mb:.0f} MB)')
    os.makedirs(f'{STAGE_DIR}/epoch_ckpts', exist_ok=True)
    for e in range(1, E + 1):
        p = os.path.join(wd, f'epoch_{e}.pth')
        if os.path.exists(p) and (e == 1 or e % 5 == 0):
            strip(p, f'{STAGE_DIR}/epoch_ckpts/epoch_{e}.pth', note)
    ev_last = evaluate(f'{STAGE_DIR}/{NAME}.pth', 'final_last')
    best = sorted(glob.glob(f'{wd}/best_*.pth'))
    ev_best = None
    if best:
        strip(best[-1], f'{STAGE_DIR}/{NAME}_best_by_val_NDS.pth', note + ' (selected by val NDS: optimistic)')
        ev_best = evaluate(f'{STAGE_DIR}/{NAME}_best_by_val_NDS.pth', 'final_best')
    for ev in (ev_last, ev_best):
        if ev and ev.get('results_json'):
            d = os.path.join(STAGE_DIR, 'predictions', ev['tag']); os.makedirs(d, exist_ok=True)
            shutil.copy(ev['results_json'], d)
    per_epoch = [dict(epoch=r.get('step'), mAP=r.get(KEY_MAP), NDS=r.get(KEY_NDS)) for r in val]
    metrics = dict(name=NAME, note='mini VAL (81 samples, 2 scenes); NOT a full nuScenes benchmark', epochs=E,
                   train_secs=rep_full.get('secs'), iters_per_epoch=rep_full.get('iters_per_epoch'), params=rep_full.get('params'),
                   final_last_epoch=ev_last, best_by_val=ev_best, per_epoch_val=per_epoch,
                   final_train_loss=rep_full.get('loss_last_quarter'), initial_train_loss=rep_full.get('loss_first_quarter'))
    json.dump(metrics, open(f'{STAGE_DIR}/metrics.json', 'w'), indent=2, default=str)
    log('FINAL last-epoch:', {k: ev_last.get(k) for k in ('mAP', 'NDS', 'ok', 'load_mismatch')})
    print('STAGE TRAIN PASS' if ev_last['ok'] else 'STAGE TRAIN FAIL')


if __name__ == '__main__':
    main()
