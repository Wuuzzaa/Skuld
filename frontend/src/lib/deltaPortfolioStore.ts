import { create } from 'zustand';

/** Eine Position im Delta-Portfolio. Nur im Browser gehalten — kein Persist. */
export type StockPosition = {
  type: 'stock';
  symbol: string;
  qty: number;
  direction: 'Long' | 'Short';
};

export type OptionPosition = {
  type: 'option';
  symbol: string;
  contract_type: 'call' | 'put';
  strike: number;
  expiry: string; // YYYY-MM-DD
  contracts: number;
  direction: 'Long' | 'Short';
};

export type Position = StockPosition | OptionPosition;

interface DeltaPortfolioState {
  positions: Position[];
  setPositions: (positions: Position[]) => void;
  addPosition: (position: Position) => void;
  removePosition: (index: number) => void;
  clear: () => void;
}

/**
 * Positionen leben nur im RAM (wie die Streamlit-Version) — bewusst kein
 * localStorage/DB-Persist. Reload = leeres Portfolio, Import erneut nötig.
 */
export const useDeltaPortfolioStore = create<DeltaPortfolioState>((set) => ({
  positions: [],
  setPositions: (positions) => set({ positions }),
  addPosition: (position) => set((s) => ({ positions: [...s.positions, position] })),
  removePosition: (index) =>
    set((s) => ({ positions: s.positions.filter((_, i) => i !== index) })),
  clear: () => set({ positions: [] }),
}));
