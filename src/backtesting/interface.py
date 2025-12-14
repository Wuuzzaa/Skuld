from dataclasses import dataclass
from typing import List, Optional, Protocol

@dataclass
class DataRequirement:
    """
    Defines a data requirement for a strategy.
    
    Attributes:
        source_table (str): The name of the physical source table in the database.
        columns (List[str]): A list of column names to include in the snapshot.
                             Use ['*'] to select all columns.
        filter_condition (Optional[str]): A SQL WHERE clause to filter the data.
                                          Example: "symbol IN ('AAPL', 'MSFT') AND expiration_date > '2023-01-01'"
                                          If None, all rows are selected (be careful!).
    """
    source_table: str
    columns: List[str]
    filter_condition: Optional[str] = None

class BacktestStrategy(Protocol):
    """
    Protocol that all strategies must implement to support backtesting data collection.
    """
    def get_data_requirements(self) -> List[DataRequirement]:
        """
        Returns a list of DataRequirements defining the data this strategy needs for backtesting.
        """
        ...
