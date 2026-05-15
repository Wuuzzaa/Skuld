'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getWatchlist, addWatchlistItem, updateWatchlistItem, deleteWatchlistItem, refreshWatchlistPrices } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, getClaudeAnalysisUrl } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Plus, Trash2, RefreshCw, ExternalLink, Save, X } from 'lucide-react';

interface WatchlistItem {
  id: number;
  symbol: string;
  company_name: string | null;
  current_price: number | null;
  sector: string | null;
  person: string | null;
  price_level_1: number | null;
  price_level_2: number | null;
  price_level_3: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export default function WatchlistPage() {
  const queryClient = useQueryClient();
  const [newSymbol, setNewSymbol] = useState('');
  const [newPerson, setNewPerson] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<Partial<WatchlistItem>>({});
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const { data: watchlist = [], isLoading } = useQuery<WatchlistItem[]>({
    queryKey: ['watchlist'],
    queryFn: getWatchlist,
  });

  const addMutation = useMutation({
    mutationFn: addWatchlistItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setNewSymbol('');
      setNewPerson('');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, any> }) => updateWatchlistItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setEditingId(null);
      setEditValues({});
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWatchlistItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      setDeleteConfirmId(null);
    },
  });

  const refreshMutation = useMutation({
    mutationFn: refreshWatchlistPrices,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }),
  });

  const handleAdd = () => {
    if (!newSymbol.trim()) return;
    addMutation.mutate({
      symbol: newSymbol.trim().toUpperCase(),
      person: newPerson.trim() || undefined,
    });
  };

  const handleSaveEdit = (id: number) => {
    updateMutation.mutate({ id, data: editValues });
  };

  const startEdit = (item: WatchlistItem) => {
    setEditingId(item.id);
    setEditValues({
      person: item.person || '',
      price_level_1: item.price_level_1,
      price_level_2: item.price_level_2,
      price_level_3: item.price_level_3,
      notes: item.notes || '',
    });
  };

  const getPriceColor = (currentPrice: number | null, level: number | null) => {
    if (!currentPrice || !level) return '';
    if (currentPrice <= level) return 'text-emerald-400 font-bold';
    return '';
  };

  if (isLoading) return <LoadingState message="Loading watchlist..." />;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Watchlist</h1>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
          Kurse aktualisieren
        </Button>
      </div>

      {/* Add new item */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex gap-2 items-end">
            <div className="flex-1 max-w-[200px]">
              <label className="text-xs text-muted-foreground mb-1 block">Symbol</label>
              <Input
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                placeholder="AAPL"
                className="h-9"
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              />
            </div>
            <div className="flex-1 max-w-[200px]">
              <label className="text-xs text-muted-foreground mb-1 block">Person</label>
              <Input
                value={newPerson}
                onChange={(e) => setNewPerson(e.target.value)}
                placeholder="Optional"
                className="h-9"
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              />
            </div>
            <Button size="sm" onClick={handleAdd} disabled={addMutation.isPending || !newSymbol.trim()}>
              <Plus className="w-4 h-4 mr-1" />
              Hinzufügen
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Watchlist Table */}
      <Card>
        <CardContent className="pt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50">
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Symbol</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Unternehmen</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Kurs</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Sektor</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Person</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Level 1</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Level 2</th>
                <th className="text-right px-3 py-2 text-xs text-muted-foreground">Level 3</th>
                <th className="text-left px-3 py-2 text-xs text-muted-foreground">Notizen</th>
                <th className="text-center px-3 py-2 text-xs text-muted-foreground">Links</th>
                <th className="text-center px-3 py-2 text-xs text-muted-foreground">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item, idx) => (
                <tr
                  key={item.id}
                  className={`border-b border-border/20 hover:bg-muted/30 transition-colors ${idx % 2 === 0 ? 'bg-muted/10' : ''}`}
                >
                  <td className="px-3 py-2 font-mono font-bold text-primary">{item.symbol}</td>
                  <td className="px-3 py-2 truncate max-w-[150px]">{item.company_name || '-'}</td>
                  <td className="px-3 py-2 text-right font-mono">{item.current_price ? formatCurrency(item.current_price) : '-'}</td>
                  <td className="px-3 py-2 text-xs truncate max-w-[120px]">{item.sector || '-'}</td>

                  {/* Editable fields */}
                  {editingId === item.id ? (
                    <>
                      <td className="px-2 py-1">
                        <Input
                          value={editValues.person || ''}
                          onChange={(e) => setEditValues({ ...editValues, person: e.target.value })}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          type="number"
                          value={editValues.price_level_1 ?? ''}
                          onChange={(e) => setEditValues({ ...editValues, price_level_1: e.target.value ? Number(e.target.value) : null })}
                          className="h-7 text-xs w-20"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          type="number"
                          value={editValues.price_level_2 ?? ''}
                          onChange={(e) => setEditValues({ ...editValues, price_level_2: e.target.value ? Number(e.target.value) : null })}
                          className="h-7 text-xs w-20"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          type="number"
                          value={editValues.price_level_3 ?? ''}
                          onChange={(e) => setEditValues({ ...editValues, price_level_3: e.target.value ? Number(e.target.value) : null })}
                          className="h-7 text-xs w-20"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          value={editValues.notes || ''}
                          onChange={(e) => setEditValues({ ...editValues, notes: e.target.value })}
                          className="h-7 text-xs"
                        />
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2">{item.person || '-'}</td>
                      <td className={`px-3 py-2 text-right font-mono ${getPriceColor(item.current_price, item.price_level_1)}`}>
                        {item.price_level_1 ? formatCurrency(item.price_level_1) : '-'}
                      </td>
                      <td className={`px-3 py-2 text-right font-mono ${getPriceColor(item.current_price, item.price_level_2)}`}>
                        {item.price_level_2 ? formatCurrency(item.price_level_2) : '-'}
                      </td>
                      <td className={`px-3 py-2 text-right font-mono ${getPriceColor(item.current_price, item.price_level_3)}`}>
                        {item.price_level_3 ? formatCurrency(item.price_level_3) : '-'}
                      </td>
                      <td className="px-3 py-2 text-xs truncate max-w-[150px]">{item.notes || '-'}</td>
                    </>
                  )}

                  {/* Links */}
                  <td className="px-2 py-2">
                    <div className="flex gap-1 justify-center">
                      <a href={`https://www.tradingview.com/chart/?symbol=${item.symbol}`} target="_blank" rel="noopener"
                        title="TradingView" className="p-1 rounded hover:bg-primary/20 transition-colors">
                        <ExternalLink className="w-3 h-3" />
                      </a>
                      <a href={getClaudeAnalysisUrl(item.symbol, item.company_name || undefined)} target="_blank" rel="noopener"
                        title="Claude AI" className="p-1 rounded hover:bg-primary/20 transition-colors text-xs font-bold">
                        AI
                      </a>
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="px-2 py-2">
                    <div className="flex gap-1 justify-center">
                      {editingId === item.id ? (
                        <>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleSaveEdit(item.id)}>
                            <Save className="w-3.5 h-3.5 text-emerald-400" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setEditingId(null); setEditValues({}); }}>
                            <X className="w-3.5 h-3.5" />
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => startEdit(item)}>
                            <span className="text-xs">✏️</span>
                          </Button>
                          {deleteConfirmId === item.id ? (
                            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => deleteMutation.mutate(item.id)}>
                              <span className="text-xs text-red-400 font-bold">!</span>
                            </Button>
                          ) : (
                            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDeleteConfirmId(item.id)}>
                              <Trash2 className="w-3.5 h-3.5 text-red-400" />
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {watchlist.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-3 py-8 text-center text-muted-foreground">
                    Keine Einträge. Füge oben ein Symbol hinzu.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Info */}
      <p className="text-xs text-muted-foreground">
        {watchlist.length} Einträge • Grüne Levels = Kurs liegt darunter (Kaufzone)
      </p>
    </div>
  );
}
