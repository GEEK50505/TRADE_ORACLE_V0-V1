import pandas as pd

fn = 'results/oracle_parameter_surface_1D_with_recent.csv'
print('Loading', fn)
df = pd.read_csv(fn)
print('Rows:', len(df))
print('Columns:', list(df.columns))

for c in ['trades_recent','win_rate_recent','expectancy_recent','total_trades','expectancy']:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

print('\nSummary of key metrics:')
print(df[['trades_recent','win_rate_recent','expectancy_recent']].describe())

mask_trades = (df['trades_recent'] >= 30) & (df['trades_recent'] <= 90)
mask_wr = df['win_rate_recent'] >= 0.45
mask_exp = df['expectancy_recent'] >= 3.0

print('\nCounts passing single gates:')
print('trades_recent 30..90:', int(mask_trades.sum()))
print('win_rate_recent >=0.45:', int(mask_wr.sum()))
print('expectancy_recent >=3.0:', int(mask_exp.sum()))

mask_all = mask_trades & mask_wr & mask_exp
print('\nCombined mask (all three):', int(mask_all.sum()))

print('\nTop 20 rows by expectancy_recent:')
print(df.sort_values('expectancy_recent', ascending=False).head(20).to_string(index=False))

print('\nExamples of parameter rows that nearly passed (trades or win_rate):')
near = df[(df['trades_recent'] >= 25) & (df['trades_recent'] <= 100)].sort_values('expectancy_recent', ascending=False).head(20)
print(near[['symbol','sma','ema','fib_min','fib_max','trades_recent','win_rate_recent','expectancy_recent']].to_string(index=False))

print('\nDone.')
