import pandas as pd

fn = 'results/oracle_parameter_surface_1D_with_recent.csv'
print('Loading', fn)
df = pd.read_csv(fn)
print('Rows:', len(df))
for c in ['total_trades','win_rate','expectancy']:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

print('\nFull-history total_trades summary:')
print(df['total_trades'].describe())
print('\nCounts for full-history gates:')
print('total_trades 30..90:', int(((df['total_trades']>=30)&(df['total_trades']<=90)).sum()))
print('win_rate>=0.45:', int((df['win_rate']>=0.45).sum()))
print('expectancy>=3.0:', int((df['expectancy']>=3.0).sum()))

mask_all = ((df['total_trades']>=30)&(df['total_trades']<=90)&(df['win_rate']>=0.45)&(df['expectancy']>=3.0))
print('\nCombined (full-history gates):', int(mask_all.sum()))

print('\nTop 20 by full-history expectancy:')
print(df.sort_values('expectancy', ascending=False).head(20).to_string(index=False))
