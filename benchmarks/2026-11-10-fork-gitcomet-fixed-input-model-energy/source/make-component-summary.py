#!/usr/bin/env python3
"""Presentation-only chart of all eight registered pairs, no new statistics."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    d=json.loads(a.analysis.read_text());assert d['complete_eight_pairs'] and d['post_characterization_passed']
    rows={x['slot']:x for x in d['all_attempts']};pair=d['selected_pairs'];fig,axes=plt.subplots(1,2,figsize=(12,5.6))
    for ax,name,title,label in zip(axes,['GPU Energy','CPU Energy'],['Native GPU model','CPU model counter — mapped unit'],['GPU model J per 60 s','CPU model J per 60 s (macmon mapping)']):
        for ids in pair:
            byapp={rows[i]['condition']:rows[i]['windows']['active_core']['components'][name]['normalized_J60'] for i in ids}
            ax.plot([0,1],[byapp['gitcomet'],byapp['fork']],color='#aaaaaa',alpha=.65,lw=1)
            ax.scatter([0,1],[byapp['gitcomet'],byapp['fork']],c=['#2677b8','#e68625'],s=37,zorder=3)
        stats=d['paired_primary_normalized_J60'][name]
        for x,key in enumerate(['gitcomet','fork']):
            mean=stats[key]['mean'];ax.plot([x-.1,x+.1],[mean,mean],color='black',lw=2,zorder=4)
            ax.annotate(f'mean {mean:.1f}',(x,mean),xytext=(14,9),textcoords='offset points',fontsize=10)
        ax.set_xticks([0,1],['GitComet','Fork']);ax.set_xlim(-.3,1.4);ax.set_title(title);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
        if name=='GPU Energy':
            diff=stats['fork_minus_gitcomet']['mean'];lo,hi=stats['ci95'];text=f'GitComet − Fork: {-diff:.1f} J60\npaired 95% CI [{-hi:.1f}, {-lo:.1f}]'
        else:
            ratio=stats['ratio'];lo,hi=ratio['ci95_log_paired'];text=f'Fork / GitComet: {ratio["geometric_mean"]:.3f}\npaired 95% CI [{lo:.3f}, {hi:.3f}]'
        annotation_y=.96 if name=='CPU Energy' else .04
        annotation_align='top' if name=='CPU Energy' else 'bottom'
        ax.text(.04,annotation_y,text,va=annotation_align,transform=ax.transAxes,fontsize=10,bbox={'facecolor':'white','alpha':.9,'edgecolor':'#dddddd'})
    fig.suptitle('History scrolling: opposing GPU and CPU model readings',fontsize=15)
    fig.text(.5,.035,'Machine-wide counters · 8 fresh-process pairs · identical posted 120 Hz input · unequal UI geometry\nCPU unit follows third-party firmware mapping · no app, battery or total-energy ranking',ha='center',fontsize=10)
    fig.subplots_adjust(left=.08,right=.98,top=.86,bottom=.2,wspace=.28)
    assert not a.output.exists();fig.savefig(a.output,dpi=150);plt.close(fig)
if __name__=='__main__':main()
