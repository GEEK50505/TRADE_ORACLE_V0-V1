import os
import sys
import traceback

p = os.path.join("data", "market_data_smoke.parquet")
print("cwd:", os.getcwd())
print("parquet path:", p)
print("exists:", os.path.exists(p))

try:
    import pandas as pd
    try:
        import pyarrow as pa
        pa_ver = pa.__version__
    except Exception:
        pa_ver = None

    print("pandas:", pd.__version__)
    print("pyarrow:", pa_ver)

    if os.path.exists(p):
        df = pd.read_parquet(p)
        print("read ok, shape:", df.shape)
        print("columns:", list(df.columns)[:12])
        print(df.head(2).to_dict())
    else:
        print("File not found; cannot read parquet.")

except Exception:
    traceback.print_exc()
    sys.exit(1)
