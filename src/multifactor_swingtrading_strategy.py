import logging
from src.logger_config import setup_logging
from config import *
from src.decorator_log_function import log_function

# enable logging
setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info(f"Start {__name__} ({__file__})")


@log_function
def calculate_multifactor_swingtrading_strategy(
        df: pd.DataFrame,
        top_percentile_value_score: float = 100,
        top_n: int = 250,
        drop_missing_values: bool = True,
        drop_weak_value_factors: bool = True,
) -> pd.DataFrame:

    # handel missing values
    if drop_missing_values:
        df = df.copy().dropna()
        logger.debug(f"df after missing values filter... shape {df.shape}")
    else:
        df = df.copy()

    # handel weak value factors
    if drop_weak_value_factors:
        df = df[
            (df['price_to_book'] >= 0.3) & (df['price_to_book'] <= 2.0) &
            (df['price_to_earnings'] >= 5) & (df['price_to_earnings'] <= 30) &
            (df['price_to_sales'] <= 2.0) &
            (df['ebitda_to_enterprise_value'] >= 0.05) &
            (df['price_to_cashflow'] > 0) &
            (df['1_year_price_appreciation'] > - 0.3)
            ]
        logger.debug(f"df after drop weak value factor filter... shape {df.shape}")

    # Value factors where low is better
    value_factors_low = [
        'price_to_book',
        'price_to_earnings',
        'price_to_sales',
        'ebitda_to_enterprise_value',
        'price_to_cashflow'
    ]

    # Value factor where high is better
    value_factor_high = 'shareholder_yield'

    # 1. Calculate percentiles for low-is-better factors (invert: 100 - percentile)
    for col in value_factors_low:
        df[f'{col}_percentile'] = (100 - df[col].rank(pct=True) * 100).round(2)

    # Calculate percentiles for high-is-better factors (use normally)
    df[f'{value_factor_high}_percentile'] = (df[value_factor_high].rank(pct=True) * 100).round(2)

    # 2. Calculate value score as SUM of percentiles (all already correctly oriented)
    percentile_cols = [f'{col}_percentile' for col in value_factors_low]
    percentile_cols.append(f'{value_factor_high}_percentile')
    df['value_score'] = df[percentile_cols].sum(axis=1).round(2)

    # 3. Filter to top X percent by value score
    threshold = df['value_score'].quantile(1 - (top_percentile_value_score / 100))
    df_filtered = df[df['value_score'] >= threshold].copy()

    # 4. Sort by value score descending and return top N stocks
    df_result = df_filtered.nlargest(top_n, 'value_score')

    # 5. Reset index and reorder columns
    df_result = df_result.reset_index(drop=True)

    # Move symbol to first column, then value_score, then rest
    cols = ['symbol', 'value_score'] + [col for col in df_result.columns if col not in ['symbol', 'value_score']]
    df_result = df_result[cols]

    return df_result

if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    import time
    import logging
    from src.logger_config import setup_logging
    from src.database import select_into_dataframe

    # enable logging
    setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info(f"Start {__name__} ({__file__})")

    start = time.time()
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'multifactor_swingtrading.sql'

    df = select_into_dataframe(sql_file_path=sql_file_path)
    df = calculate_multifactor_swingtrading_strategy(df)
    ende = time.time()

