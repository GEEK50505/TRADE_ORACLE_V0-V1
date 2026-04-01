import pandas as pd
import argparse

p = argparse.ArgumentParser()
p.add_argument('--oracle', default='results/oracle_parameter_surface_1D_with_recent.csv')
p.add_argument('--min-trades', type=int, default=5)
p.add_argument('--max-trades', type=int, default=200)
p.add_argument('--min-win', type=float, default=0.40)
p.add_argument('--min-expect', type=float, default=1.0)
p.add_argument('--top-n', type=int, default=100)
args = p.parse_args()

print('Loading', args.oracle)
df = pd.read_csv(args.oracle)
for c in ['trades_recent','win_rate_recent','expectancy_recent']:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

mask = (
    (df['trades_recent'] >= args.min_trades) &
    (df['trades_recent'] <= args.max_trades) &
    (df['win_rate_recent'] >= args.min_win) &
    (df['expectancy_recent'] >= args.min_expect)
)

cands = df[mask].copy()
print('Candidates found:', len(cands))
if len(cands) == 0:
    print('No candidates with current thresholds.')
else:
    top = cands.sort_values('expectancy_recent', ascending=False).head(args.top_n)
    out = 'results/top_100_parameters.csv'
    top.to_csv(out, index=False)
    print('Wrote', out, 'rows=', len(top))
