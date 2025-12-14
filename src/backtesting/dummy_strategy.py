from typing import List
from src.backtesting.interface import BacktestStrategy, DataRequirement

class DummyStrategy(BacktestStrategy):
    def __init__(self, table_name: str = "OptionDataYahoo"):
        self.table_name = table_name

    def get_data_requirements(self) -> List[DataRequirement]:
        return [
            DataRequirement(
                source_table=self.table_name,
                columns=["symbol", "expiration_date", "strike", "option_type", "last_price"],
                filter_condition="symbol = 'A'"
            )
        ]
