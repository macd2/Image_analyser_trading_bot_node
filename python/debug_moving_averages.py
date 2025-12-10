import pandas as pd
import pandas_ta as ta
import numpy as np

# Create simple test data
df = pd.DataFrame({
    'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120]
})

# Test moving averages
sma_20 = ta.sma(df['close'], length=20)
sma_50 = ta.sma(df['close'], length=50)
sma_200 = ta.sma(df['close'], length=200)

print("SMA_20:", sma_20.tolist())
print("SMA_50:", sma_50.tolist())
print("SMA_200:", sma_200.tolist())