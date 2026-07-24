import pandas as pd
import sys

try:
    df = pd.read_excel('SC5001_2025S2.xls', engine='xlrd', header=None)
    for i, row in df.iterrows():
        print(f"Row {i}: {row.to_list()}")
        if i > 50:
            break
except Exception as e:
    print(f"Error: {e}")
