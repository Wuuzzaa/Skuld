import time
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.massiv_api import get_symbols
from src.logger_config import setup_logging, get_log_level_from_db
from src.database import drop_all_views, get_postgres_engine, recreate_views, run_migrations
from src.send_alert import send_telegram_message
from src.massiv_api import load_option_chains
from src.sp500_symbols_wiki import load_sp500_constituents_from_wikipedia
from src.stock_volatility import calculate_and_store_stock_historical_volatility_history, calculate_and_store_stock_implied_volatility_history
from src.technical_indicators import calc_technical_indicators, calc_technical_indicators_history
from src.yahoo_asset_profile import load_asset_profile
from src.yahoo_dividens import calculate_dividend_classification, calculate_dividend_classification_history, calculate_dividend_classification_history_full
from src.yahooquery_earning_dates import scrape_earning_dates
from src.yahooquery_financials import generate_fundamental_data, load_historical_prices, load_stock_prices
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.historization import create_history_tables_and_views, generate_table_functions_for_history_enabled_views, generate_time_travel_views_for_history_enabled_views, run_historization_pipeline
from src.pipeline_monitor import PipelineMonitor

logger = logging.getLogger(__name__)

def db_setup():
    """Set up the database with migrations and history tables/views."""
    logger.info("###### Dropping all views to avoid dependency issues during migrations...")
    drop_all_views(get_postgres_engine())
    logger.info("###### Running database migrations...")
    run_migrations()
    logger.info("###### Creating history tables and views...")
    create_history_tables_and_views()
    logger.info("###### Recreating views...")
    recreate_views()
    create_history_tables_and_views()
    logger.info("###### Generating table functions for history-enabled views...")
    generate_table_functions_for_history_enabled_views()
    generate_time_travel_views_for_history_enabled_views()

def main(args):
    pipeline = None
    logger.info(f"Mode: {args.mode}")

    if args.mode == "only_run_migrations":
        logger.info("#" * 80)
        logger.info("Running database migrations only...")
        logger.info("#" * 80)
        try:
            logger.info("###### Setting up database...")
            db_setup()
            
            logger.info("#" * 80)
            logger.info("Database migrations done. Exit main")
            logger.info("#" * 80)
            send_telegram_message(
                "Info - DB Migrations",
                "✅ Database migrations completed successfully on container start."
            )
        except Exception as e:
            logger.error(f"Database migrations failed: {e}", exc_info=True)
            send_telegram_message(
                "Alert - DB Migrations Failed",
                f"❌ Database migrations failed on container start.\n\n<b>Error:</b>\n<code>{e}</code>"
            )
            raise
        return 0

    try:
        # Initialize Pipeline Monitor with the specific mode
        pipeline = PipelineMonitor(mode=args.mode)
        pipeline.start()
        
        run_successful = False

        db_setup()

        logger.info("#" * 80)
        logger.info(f"Starting Data Collection Pipeline")
        logger.info("#" * 80)

        symbols = get_symbols()

        # define the data collection tasks to run based on the mode
        task_map = {
            "all": [
                ("Massive Option Chains", load_option_chains, (symbols["options"],)),
                ("Fetch Current Stock Day Prices", load_stock_prices, (symbols["all"],)),
                ("Yahoo Finance Analyst Price Targets", scrape_yahoo_finance_analyst_price_targets, (symbols["stocks"],)),
                ("Earning Dates", scrape_earning_dates, (symbols["stocks"],)),
                ("Yahoo Query Fundamentals", generate_fundamental_data, (symbols["stocks"],)),
                ("Yahoo Dividends", calculate_dividend_classification, ()),
                ("Yahoo Asset Profiles", load_asset_profile, (symbols["all"],)),
                ("Technical Indicators", calc_technical_indicators, (symbols["all"],)),
            ],
            "saturday_night": [
                ("Yahoo Dividends", calculate_dividend_classification, ()),
                ("Yahoo Query Fundamentals", generate_fundamental_data, (symbols["stocks"],)),
                ("Yahoo Finance Analyst Price Targets", scrape_yahoo_finance_analyst_price_targets, (symbols["stocks"],)),
                ("Earning Dates", scrape_earning_dates, (symbols["stocks"],)),
                ("Yahoo Asset Profiles", load_asset_profile, (symbols["all"],)),
                ("S&P500 Constituents", load_sp500_constituents_from_wikipedia, ()),
            ],
            "market_start_mid_end": [
                ("Fetch Current Stock Day Prices", load_stock_prices, (symbols["all"],)),
            ],
            "stock_data_daily": [
                ("Technical Indicators", calc_technical_indicators, (symbols["all"],)),
            ],
            "option_data": [
                ("Massive Option Chains", load_option_chains, (symbols["options"],)),
            ],
            "historical_technical_indicators": [
                # ("Technical Indicators History", calc_technical_indicators_history, (symbols["all"],)),
            ],
            "historical_prices": [
                ("Historical Prices", load_historical_prices, (symbols["all"],)),
            ],
            "historical_iv": [
                ("Historical IV", calculate_and_store_stock_implied_volatility_history, ()),
            ],
            "historical_volatility": [
                ("Historical Volatility", calculate_and_store_stock_historical_volatility_history, ()),
            ],
            "historical_dividend_classification": [
                ("Historical Volatility", calculate_dividend_classification_history, ()),
            ],
            "sp500_constituents": [
                ("S&P500 Constituents", load_sp500_constituents_from_wikipedia, ()),
            ],
        }

        parallel_tasks = task_map.get(args.mode)

        
        if args.mode == "historical_full":
            load_historical_prices(symbols["all"])
            calculate_and_store_stock_historical_volatility_history()
            calc_technical_indicators_history(symbols)
            calculate_dividend_classification_history_full()
        elif args.mode == "historical_technical_indicators":
            calc_technical_indicators_history(symbols["all"])
        elif args.mode == "historization":
            parallel_tasks = []
        elif args.mode not in task_map:
            raise ValueError(f"Unknown mode: {args.mode}")

        if parallel_tasks:
            # log mode and task names
            task_names = [task[0] for task in parallel_tasks]
            logging.info(f"Run mode: {args.mode} with tasks: {task_names}")

            max_workers = MAX_WORKERS if MAX_WORKERS > 0 else len(parallel_tasks)
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Max workers: {max_workers}")
            if max_workers < len(parallel_tasks):
                logger.info(f"Running {len(parallel_tasks)} data collection tasks with max {max_workers} parallel workers")
                logger.info(f"{'=' * 80}\n")
            else:
                logger.info(f"Running ALL {len(parallel_tasks)} data collection tasks in parallel")
            logger.info(f"{'=' * 80}\n")

            parallel_start = time.time()


            # Use ThreadPoolExecutor for I/O-bound tasks (web scraping)
            # Set max_workers to number of tasks (they're all I/O bound)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(pipeline.run_task, name, func, *args): name
                    for name, func, args in parallel_tasks
                }

                try:
                    for future in as_completed(future_to_task):
                        task_name = future_to_task[future]
                        try:
                            # run_task returns: task_name, result, error, mem_diff, peak_mem, duration
                            ret_name, result, error, mem_diff, peak_mem, duration = future.result()
                            pipeline.record_result(ret_name, result, error, mem_diff, peak_mem)
                            
                        except Exception as e:
                            logger.error(f"Critical error in {task_name}: {e}")
                            # In case future.result() itself raises
                            pipeline.record_result(task_name, None, e, 0, 0)
                except KeyboardInterrupt:
                    logger.warning("KeyboardInterrupt received! Shutting down executor...")
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise

            parallel_duration = int(time.time() - parallel_start)
            pipeline.set_parallel_duration(parallel_duration)
            
            logger.info(f"\n{'=' * 80}")
            logger.info(f"All parallel tasks completed in {parallel_duration}s")
            logger.info(f"{'=' * 80}\n")

        if args.mode == "historization" or args.mode == "all":
            # Historization
            run_historization_pipeline()
        run_successful = True

    except Exception as e:
        # We catch exceptions to allow finally to run, but we want to re-raise them
        # if they imply a crash.
        logger.error(f"Critical failure in main pipeline: {e}", exc_info=True)
        raise

    finally:
        if pipeline:
            pipeline.stop()
            
            # Generator and log report
            report, _ = pipeline.generate_report(run_successful)
            
            logger.info("\n" + "#" * 80)
            logger.info("DATA COLLECTION PIPELINE SUMMARY")
            logger.info("#" * 80)
            logger.info(report)
            logger.info("#" * 80 + "\n")
            
            # Send Telegram message
            try:
                pipeline.send_telegram_summary(run_successful)
            except Exception as e:
                logger.error(f"Failed to send Telegram summary: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Collection Script")
    parser.add_argument("--mode", type=str, required=True,
                        choices=[
                            "all",
                            "saturday_night",
                            "market_start_mid_end",
                            "stock_data_daily",
                            "option_data",
                            "historical_prices",
                            "historical_iv",
                            "historical_volatility",
                            "historical_technical_indicators",
                            "historical_dividend_classification",
                            "historical_full",
                            "historization",
                            "only_run_migrations",
                            "sp500_constituents"
                        ],
                        help="Mode for data collection")
    parser.add_argument("--env", type=str, required=False, default=None,
                        help="Environment name (e.g. Staging, Prod)")
    args = parser.parse_args()

    # Log component based on mode for separate log directories
    MODE_COMPONENTS = {
        "historization": "historization",
        "historical_prices": "historical",
        "historical_iv": "historical",
        "historical_technical_indicators": "historical",
        "historical_full": "historical",
        "only_run_migrations": "migrations",
    }
    log_component = MODE_COMPONENTS.get(args.mode, "data_collector")
    
    # Get log level from database if available, otherwise use INFO as default
    try:
        log_level = get_log_level_from_db()
    except Exception:
        log_level = logging.INFO
    
    setup_logging(component=log_component, log_level=log_level, console_output=True)
    logger.info(f"Starting {log_component} (mode: {args.mode})")

    if args.env:
        os.environ['SKULD_ENV'] = args.env

    main(args)

