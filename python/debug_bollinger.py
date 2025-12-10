import pandas as pd
import pandas_ta as ta
import numpy as np

# Create simple test data
df = pd.DataFrame({
    'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
})

# Test Bollinger Bands
bb = ta.bbands(df['close'], length=5)
print("Bollinger Bands columns:", bb.columns.tolist())
print("Bollinger Bands data:")
print(bb)