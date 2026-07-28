# Screener Table Redesign — Roll & Screen

**Date:** 2026-07-18  
**Branch:** feature/roll-and-screen  
**File:** `pages/roll_and_screen.py`

---

## Problem

1. **Dark-mode bleed-through:** `_inject_css()` hardcodes `background: #0b1120` directly on `.stApp`, overriding Streamlit's theme setting regardless of user preference.
2. **Tile layout:** `_render_screener_cards()` renders dense 3-wide or 5-wide card grids. With 100+ candidates the cards are tiny and hard to scan. No color cues on key metrics.

---

## Solution

### 1. Theme-Adaptive CSS

Replace hardcoded dark colors in `_inject_css()` with theme-sensitive selectors:

```css
/* Dark mode */
[data-theme="dark"] {
  --bg-base:   #0b1120;
  --bg-card:   #131e30;
  --bg-border: #243549;
  --text-primary: #f1f5f9;
  --text-muted:   #94a3b8;
}

/* Light mode */
[data-theme="light"] {
  --bg-base:   #f8fafc;
  --bg-card:   #ffffff;
  --bg-border: #e2e8f0;
  --text-primary: #0f172a;
  --text-muted:   #64748b;
}

.stApp { background: var(--bg-base) !important; color: var(--text-primary) !important; }
```

Accent colors (teal, green, amber, red) remain unchanged — they work in both themes.

---

### 2. Screener Table (replaces `_render_screener_cards`)

**New function:** `_render_screener_table(df, sel_key)`

Renders a single custom HTML `<table>` for all candidates (Top-5 + rest unified).

#### Columns

| Col | Content | Styling |
|-----|---------|---------|
| Symbol | Ticker, bold mono 16px | — |
| Ann.% | Annualized return | Green ≥15%, Amber 8–15%, Red <8% |
| DTE | Days to expiry | Neutral mono |
| IV-Rank | Numeric badge | Red pill ≥60, Amber ≥30, Gray <30 |
| Score | Mini bar + `7/9` | Bar fills proportionally, color = score_color |
| Sektor | Emoji + text | Muted, small |
| (action) | `→` button per row | Streamlit button, triggers state + rerun |

#### Row styling

- Row height: ~52px, padding 10px 14px
- Top-5 rows: subtle left border accent (teal, 3px) + `★` prefix on symbol
- Hover: light background tint (theme-sensitive)
- Selected row: teal left border + teal background tint

#### Interaction

`→` button at end of each row sets `st.session_state[sel_key] = sym` and calls `st.rerun()`. Keeps existing detail-panel logic below the table unchanged.

#### No more expander

Top-5 and rest in one table — no "weitere Kandidaten" expander needed. Rows are compact enough to scroll.

---

## Out of Scope

- Roller tab: no changes
- Filter panel: no changes
- Detail analysis panel below table: no changes
- Score logic / SQL queries: no changes
