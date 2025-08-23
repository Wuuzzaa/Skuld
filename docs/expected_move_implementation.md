# Expected Move Implementation

This document explains the implementation of the Expected Move metric in the Skuld options trading system.

## What is Expected Move?

The Expected Move is a key options metric that estimates the potential price range of an underlying asset over a given period, derived from implied volatility. It represents approximately one standard deviation of expected price movement.

## Formula

```
Expected Move ($) = Stock Price × Implied Volatility × √(Days to Expiration / 365)
Expected Move (%) = (Expected Move $ / Stock Price) × 100
```

## Implementation

### Function: `calculate_expected_move`

**Location:** `src/spreads_calculation.py`

**Parameters:**
- `underlying_price` (float): Current price of the underlying asset
- `days_to_expiration` (int): Number of days until expiration
- `implied_volatility` (float): Implied volatility (e.g., 0.25 for 25%)

**Returns:**
- Dictionary with 'dollar' (absolute move in $) and 'percent' (percentage move)

### Integration

The Expected Move calculation is integrated into:

1. **Spreads Calculation (`get_spreads`):**
   - Added `expected_move_dollar` column
   - Added `expected_move_percent` column

2. **Iron Condors Calculation (`get_iron_condors`):**
   - Added `expected_move_dollar` column  
   - Added `expected_move_percent` column

3. **Streamlit UI:**
   - Automatically displays in `/pages/spreads.py`
   - Automatically displays in `/pages/iron_condors.py`

## Example Usage

```python
from src.spreads_calculation import calculate_expected_move

# Example: AAPL at $150, 30 days to expiration, 25% IV
result = calculate_expected_move(150.0, 30, 0.25)
print(f"Expected Move: ${result['dollar']:.2f} ({result['percent']:.2f}%)")
# Output: Expected Move: $10.75 (7.17%)
```

## Test Coverage

Comprehensive tests are included in `tests/test_expected_move.py`:

- Basic calculation validation
- Edge case handling (zero/negative values)
- Real market scenarios
- Precision validation  
- Consistency with existing POP calculation

## Benefits for Strategy Evaluation

The Expected Move metric improves strategy evaluation by:

1. **Risk Assessment:** Understanding the likely price range helps assess if option strikes are within or outside the expected move
2. **Strategy Selection:** Helps choose between strategies based on market outlook vs. expected volatility
3. **Position Sizing:** Informs appropriate position sizing based on expected price movement
4. **Profit Probability:** Complements existing POP calculations with volatility-based expectations

## Display Format

- **Dollar Amount:** Displayed as currency with 2 decimal places (e.g., $10.75)
- **Percentage:** Displayed as percentage with 2 decimal places (e.g., 7.17%)

Both values appear as additional columns in the spreads and iron condors tables, providing immediate insight into expected volatility for each underlying asset.