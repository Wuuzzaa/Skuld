"""Watchlist router - CRUD for user watchlist items (file-based JSON storage)."""

import json
import os
import shutil
import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from api.core.auth import get_current_user
from api.core.database import query_dataframe

router = APIRouter()

# File paths
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
BACKUP_DIR = DATA_DIR / "backups"


class WatchlistItem(BaseModel):
    id: int
    symbol: str
    company_name: Optional[str] = None
    current_price: Optional[float] = None
    sector: Optional[str] = None
    person: Optional[str] = None
    price_level_1: Optional[float] = None
    price_level_2: Optional[float] = None
    price_level_3: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WatchlistCreate(BaseModel):
    symbol: str
    person: Optional[str] = None
    price_level_1: Optional[float] = None
    price_level_2: Optional[float] = None
    price_level_3: Optional[float] = None
    notes: Optional[str] = None


class WatchlistUpdate(BaseModel):
    symbol: Optional[str] = None
    person: Optional[str] = None
    price_level_1: Optional[float] = None
    price_level_2: Optional[float] = None
    price_level_3: Optional[float] = None
    notes: Optional[str] = None


def _load_watchlist() -> List[dict]:
    """Load watchlist from JSON file."""
    if not WATCHLIST_FILE.exists():
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_watchlist(items: List[dict]):
    """Save watchlist to JSON file with backup."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Create backup before saving
    if WATCHLIST_FILE.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"watchlist_{timestamp}.json"
        shutil.copy2(WATCHLIST_FILE, backup_path)
        _cleanup_old_backups()

    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def _cleanup_old_backups(keep_days: int = 3):
    """Remove backup files older than keep_days."""
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=keep_days)
    for backup_file in BACKUP_DIR.glob("watchlist_*.json"):
        try:
            mtime = datetime.datetime.fromtimestamp(backup_file.stat().st_mtime)
            if mtime < cutoff:
                backup_file.unlink()
        except OSError:
            pass


def _next_id(items: List[dict]) -> int:
    """Get next available ID."""
    if not items:
        return 1
    return max(item.get("id", 0) for item in items) + 1


def _auto_fill_from_stock_data(symbol: str) -> dict:
    """Fetch company_name, live_stock_price, and sector from StockData (read-only query)."""
    try:
        df = query_dataframe(
            'SELECT company_name, live_stock_price, company_sector FROM "StockData" WHERE symbol = :symbol LIMIT 1',
            {"symbol": symbol.upper()}
        )
        if df.empty:
            return {"company_name": None, "current_price": None, "sector": None}
        row = df.iloc[0]
        return {
            "company_name": row.get("company_name"),
            "current_price": float(row["live_stock_price"]) if row.get("live_stock_price") is not None else None,
            "sector": row.get("company_sector"),
        }
    except Exception:
        return {"company_name": None, "current_price": None, "sector": None}


@router.get("/")
async def get_watchlist(current_user: dict = Depends(get_current_user)):
    """Get all watchlist entries."""
    return _load_watchlist()


@router.post("/")
async def add_watchlist_item(item: WatchlistCreate, current_user: dict = Depends(get_current_user)):
    """Add a new item to the watchlist. Auto-fills company data from StockData."""
    items = _load_watchlist()
    symbol = item.symbol.upper()
    auto = _auto_fill_from_stock_data(symbol)
    now = datetime.datetime.now().isoformat()

    new_item = {
        "id": _next_id(items),
        "symbol": symbol,
        "company_name": auto["company_name"],
        "current_price": auto["current_price"],
        "sector": auto["sector"],
        "person": item.person,
        "price_level_1": item.price_level_1,
        "price_level_2": item.price_level_2,
        "price_level_3": item.price_level_3,
        "notes": item.notes,
        "created_at": now,
        "updated_at": now,
    }

    items.append(new_item)
    _save_watchlist(items)
    return {"status": "created", "symbol": symbol, "item": new_item}


@router.put("/{item_id}")
async def update_watchlist_item(item_id: int, item: WatchlistUpdate, current_user: dict = Depends(get_current_user)):
    """Update a watchlist entry."""
    items = _load_watchlist()
    target = next((i for i in items if i.get("id") == item_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    if item.symbol is not None:
        symbol = item.symbol.upper()
        auto = _auto_fill_from_stock_data(symbol)
        target["symbol"] = symbol
        target["company_name"] = auto["company_name"]
        target["current_price"] = auto["current_price"]
        target["sector"] = auto["sector"]

    if item.person is not None:
        target["person"] = item.person
    if item.price_level_1 is not None:
        target["price_level_1"] = item.price_level_1
    if item.price_level_2 is not None:
        target["price_level_2"] = item.price_level_2
    if item.price_level_3 is not None:
        target["price_level_3"] = item.price_level_3
    if item.notes is not None:
        target["notes"] = item.notes

    target["updated_at"] = datetime.datetime.now().isoformat()
    _save_watchlist(items)
    return {"status": "updated"}


@router.delete("/{item_id}")
async def delete_watchlist_item(item_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a watchlist entry."""
    items = _load_watchlist()
    new_items = [i for i in items if i.get("id") != item_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    _save_watchlist(new_items)
    return {"status": "deleted"}


@router.post("/refresh-prices")
async def refresh_watchlist_prices(current_user: dict = Depends(get_current_user)):
    """Refresh all prices and company data from StockData (read-only DB query)."""
    items = _load_watchlist()
    if not items:
        return {"status": "no items"}

    for item in items:
        auto = _auto_fill_from_stock_data(item["symbol"])
        item["current_price"] = auto["current_price"]
        item["company_name"] = auto["company_name"]
        item["sector"] = auto["sector"]
        item["updated_at"] = datetime.datetime.now().isoformat()

    _save_watchlist(items)
    return {"status": "refreshed", "count": len(items)}
