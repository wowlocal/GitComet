from pathlib import Path
import json, hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

D=Path(__file__).resolve().parent
r=json.loads((D/'analysis.json').read_text())
pairs=[(r['runs'][a-1],r['runs'][b-1]) for a,b in [(1,2),(4,3),(6,5),(7,8)]]
metrics=[('Held logical-pose pairs (%)',lambda x:100*x['core']['held_pair_fraction'],(0,2.5)),('Actual presentations / second',lambda x:x['core']['presentation_rate_hz'],(0,125)),('App CPU (% of one core)',lambda x:x['telemetry']['scrolling']['app_cpu_percent_one_core'],(0,35)),('Source-equivalent pose lag (ms)',lambda x:x['core']['source_equivalent_pose_lag_ms']['median'],(0,60))]
fig,axes=plt.subplots(1,4,figsize=(12,3.4))
for ax,(title,getter,lim) in zip(axes,metrics):
    for i,(off,on) in enumerate(pairs):
        ax.plot([0,1],[getter(off),getter(on)],color='#718096',alpha=.7,lw=1,zorder=1)
        ax.scatter([0,1],[getter(off),getter(on)],c=['#e8873d','#2977c9'],s=30,zorder=2)
    ax.set(title=title,ylim=lim,xticks=[0,1],xticklabels=['Off','On'],xlim=(-.25,1.25))
    ax.grid(axis='y',alpha=.18);ax.spines[['top','right']].set_visible(False)
fig.suptitle('Same installed binary · four adjacent replay pairs · no physical-input claim',fontsize=12)
fig.text(.5,.015,'Logical coordinates are not raster pixels. On deliberately uses a 12.5 ms source lookback; source-equivalent lag is not hardware input latency.',ha='center',fontsize=8)
fig.tight_layout(rect=[0,.06,1,.92])
fig.savefig(D/'comparison.png',dpi=180);fig.savefig(D/'comparison.svg');plt.close(fig)
(D/'plot.py').write_text(Path(__file__).read_text().replace("D=Path(__file__).resolve().parent","D=Path(__file__).resolve().parent"))
hashes={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest()for p in D.rglob('*')if p.is_file()and p.name!='SHA256SUMS.json'}
(D/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2)+'\n')
