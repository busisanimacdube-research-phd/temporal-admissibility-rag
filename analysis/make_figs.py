import json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RES = os.path.join(HERE, 'results')
OUT = os.path.join(HERE, 'figures')
os.makedirs(OUT, exist_ok=True)
C_BLUE, C_GREEN, C_YG, C_GREY = ('#31688E', '#35B779', '#B5DE2B', '#7F7F7F')
NAMES = {'bm25': 'BM25', 'dense': 'Dense', 'hybrid': 'Hybrid', 'lightrag': 'LightRAG\n(inspired)', 'hipporag': 'HippoRAG\n(inspired)', 'visrag': 'VisRAG\n(inspired)', 'm3docrag': 'M3DocRAG\n(inspired)'}
FAMILIES = {'fact_at_date': 'Fact at date', 'restatement': 'Revised figure', 'crossmodal': 'Cross-modal', 'multihop_temporal': 'Multi-hop', 'unanswerable_at_tau': 'Not yet reported', 'ratio': 'Ratio', 'period_comparison': 'Period comparison'}
plt.rcParams.update({'font.size': 12, 'font.family': 'serif', 'axes.grid': True, 'grid.alpha': 0.3, 'axes.axisbelow': True})

def leakage():
    d = json.load(open(os.path.join(RES, 'leakage.json')))['systems']
    rows = [(NAMES[s], d[s]['evidence_leak_q'][0], d[s]['leaked_unit_share'], d[s]['answer_leak'][0]) for s in NAMES]
    fig, ax = plt.subplots(figsize=(6.6, 4.5))
    w = 0.27
    for j, (lab, col) in enumerate((('Questions with inadmissible evidence ($\\mathrm{EL}_q$)', C_BLUE), ('Inadmissible share of retrieved units ($\\mathrm{EL}_u$)', C_GREEN), ('Pre-revision answers with the later value ($\\mathrm{AL}$)', C_YG))):
        xs = [i + (j - 1) * w for i in range(len(rows))]
        vals = [r[j + 1] for r in rows]
        ax.bar(xs, vals, w, label=lab, color=col)
        for x, v in zip(xs, vals):
            ax.annotate(f'{v:.0f}', (x, v), ha='center', va='bottom', fontsize=7, xytext=(0, 1), textcoords='offset points')
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r[0] for r in rows], fontsize=9)
    base = json.load(open(os.path.join(RES, 'base_rate.json')))['base_rate_mean']
    ax.axhline(base, color=C_GREY, linestyle='--', linewidth=1, label=f'Base rate of inadmissible units ({base:.1f})')
    ax.set_ylabel('Share (%)')
    ax.set_ylim(0, 108)
    fig.legend(frameon=False, loc='upper center', ncol=1, fontsize=9, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.8))
    fig.savefig(os.path.join(OUT, 'fig_leakage.pdf'))

def lead_time():
    d = json.load(open(os.path.join(RES, 'lead_days.json')))
    data = [[x / 365.25 for x in d[s]] for s in NAMES]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bp = ax.boxplot(data, vert=False, widths=0.55, patch_artist=True, showfliers=False, medianprops={'color': C_BLUE, 'linewidth': 2}, whiskerprops={'color': C_GREY}, capprops={'color': C_GREY})
    for b in bp['boxes']:
        b.set(facecolor=C_GREEN, alpha=0.55, edgecolor=C_GREEN)
    ax.axvline(1, color=C_GREY, linestyle='--', linewidth=1)
    ax.set_yticks(range(1, len(NAMES) + 1))
    ax.set_yticklabels([n.replace('\n', ' ') for n in NAMES.values()], fontsize=10)
    ax.set_xlabel('Years between the as-of date and the publication of leaked evidence')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'fig_lead_time.pdf'))

def filter_family():
    d = json.load(open(os.path.join(RES, 'leakage.json')))['paired']['hybrid_vs_timefiltered']['by_family']
    rows = sorted(((FAMILIES[k], v['first'], v['second'], v['n']) for k, v in d.items()), key=lambda r: r[2] - r[1])
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    h = 0.38
    for j, (lab, col, idx) in enumerate((('Hybrid', C_BLUE, 1), ('Hybrid with as-of filter', C_GREEN, 2))):
        ys = [i + (0.5 - j) * h for i in range(len(rows))]
        vals = [r[idx] for r in rows]
        ax.barh(ys, vals, h, label=lab, color=col)
        for y, v in zip(ys, vals):
            ax.annotate(f'{v:.1f}', (v, y), ha='left', va='center', fontsize=8, xytext=(2, 0), textcoords='offset points')
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f'{r[0]} ($n={r[3]}$)' for r in rows], fontsize=10)
    ax.set_xlabel('Accuracy (%)')
    ax.set_xlim(0, 105)
    fig.legend(frameon=False, loc='upper center', ncol=2, fontsize=10, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, 'fig_filter_family.pdf'))
if __name__ == '__main__':
    leakage()
    lead_time()
    filter_family()
