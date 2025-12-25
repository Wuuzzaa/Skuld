JMS_DOC = """
## Joachims Milchmädchenrechnungs Score (JMS)

JMS is a calculated score that represents a simplified expected value based on the delta of the short option, a mental stop loss, and a take profit goal. The score is normalized using the Buying Power Reduction (BPR).

### Calculation

The JMS score allows different underlyings to be compared, providing a quick overview of their relative performance. A higher JMS score indicates a better trade setup.

**Current Settings:**
- **Take Profit Goal:** 60% of the maximum profit (JMS_TP_GOAL = 0.6)
- **Mental Stop Loss:** 200% loss relative to the collected premium (JMS_MENTAL_STOP = 2)

This means that a position is closed when it reaches 60% of the maximum profit or when the loss reaches 200% of the collected premium.
"""

JMS_FORMULA = r"JMS = \frac{\text{Expected Win Value} - \text{Expected Loss Value}}{\text{BPR}} \times 100"

JMS_DETAILS = r"""
\begin{aligned}
\text{Expected Win Value} &= \text{Win Probability} \times \text{Potential Win} \\
\text{Expected Loss Value} &= \text{Potential Loss} \times \text{Loss Probability} \\
\text{Win Probability} &= 1 - |\text{Short Option Delta}| \\
\text{Loss Probability} &= 1 - \text{Win Probability} \\
\text{Potential Win} &= \text{Max Profit} \times \text{Take Profit Goal} \\
\text{Potential Loss} &= \text{Max Profit} \times \text{Mental Stop}
\end{aligned}
"""
