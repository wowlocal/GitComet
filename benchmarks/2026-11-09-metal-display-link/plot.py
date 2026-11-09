from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
data=json.loads((root/'analysis.json').read_text())
metrics=[
    ('Actual presentation rate',lambda r:r['core']['presentation_rate_hz'],'presentations / second'),
    ('Submission elapsed time',lambda r:r['cpu_submit_including_drawable_acquisition_ms']['median'],'median ms / submission'),
    ('Application CPU',lambda r:r['telemetry']['scrolling']['app_cpu_percent_one_core'],'percent of one CPU core'),
    ('Whole-GPU modeled power',lambda r:r['telemetry']['scrolling']['whole_gpu_modeled_w'],'modeled watts'),
]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':13,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white'})
fig,axes=plt.subplots(2,2,figsize=(10.5,7.2))
colors=['#277da8','#d47821']
for ax,(title,getter,unit) in zip(axes.flat,metrics):
    for pair in range(4):
        rs=data['runs'][pair*2:pair*2+2]
        a=next(r for r in rs if r['condition']=='stock')
        b=next(r for r in rs if r['condition']=='fixed')
        shift=(pair-1.5)*.025
        ax.plot([shift,1+shift],[getter(a),getter(b)],color='#b4bdc7',linewidth=1.2,zorder=1)
        ax.scatter([shift,1+shift],[getter(a),getter(b)],c=colors,s=45,zorder=2)
    ax.set(title=title,ylabel=unit,xticks=[0,1],xticklabels=['Stock GPUI','PR #47'],xlim=(-.3,1.3))
    ax.grid(axis='y',alpha=.2)
    if 'submission' in title:ax.set_ylim(0,6)
fig.suptitle('Matched GitComet releases: stock vs CAMetalDisplayLink',fontsize=16,x=.06,ha='left',y=.99)
fig.text(.06,.94,'Apple M5 Max · 120 Hz built-in display · 4 runs per condition · identical app and input',fontsize=11,color='#46515d')
fig.text(.06,.055,'Lines connect adjacent stock/fix pairs. Presentation rate uses fixed sustained-motion cores.\nCPU and power use the full replay phase. Lower power accompanies fewer presentations;\nthis does not establish an efficiency or smoothness improvement. Instrumented synthetic replay.',fontsize=9.5,color='#46515d',linespacing=1.5)
fig.subplots_adjust(left=.10,right=.97,top=.87,bottom=.22,hspace=.52,wspace=.40)
fig.savefig(root/'comparison.png',dpi=180)
