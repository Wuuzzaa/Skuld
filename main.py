import argparse
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.barchart_scrapper import scrape_barchart
from src.live_stock_price_collector import fetch_current_prices
from src.logger_config import setup_logging
from src.database import run_migrations
from src.massiv_api import load_option_chains
from src.tradingview_optionchain_scrapper import scrape_option_data_trading_view
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.yahooquery_earning_dates import scrape_earning_dates
from src.yahooquery_option_chain import get_yahooquery_option_chain
from src.yahooquery_financials import generate_fundamental_data
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.google_drive_upload import upload_database
from src.dividend_radar import process_dividend_data
from config_utils import get_filtered_symbols_and_dates_with_logging, get_filtered_symbols_with_logging
from config_utils import generate_expiry_dates_from_rules
from src.historization import run_historization_pipeline
from src.util import log_memory_usage, MemoryMonitor, executed_as_github_action

setup_logging(component="data_collector", log_level=logging.INFO, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start SKULD")


def run_task_with_timing(task_name, func, *args, **kwargs):
    """Helper function to run a task with timing and error handling"""
    start = time.time()
    logger.info("#" * 80)
    logger.info(f"Starting: {task_name}")
    start_mem = log_memory_usage(f"[MEM] Start {task_name}: ")
    logger.info("#" * 80)

    try:
        result = func(*args, **kwargs)
        duration = int(time.time() - start)
        end_mem = log_memory_usage(f"[MEM] End {task_name}: ")

        mem_diff = 0
        peak_mem = 0
        if start_mem is not None and end_mem is not None:
            mem_diff = end_mem - start_mem
            peak_mem = end_mem
            logger.info(f"[MEM] {task_name} consumed: {mem_diff:+.2f} MB")

        logger.info(f"✓ {task_name} - Done - Runtime: {duration}s")
        return result, None, mem_diff, peak_mem
    except Exception as e:
        duration = int(time.time() - start)
        log_memory_usage(f"[MEM] Fail {task_name}: ")
        logger.error(f"✗ {task_name} - Failed after {duration}s: {e}")
        return None, e, 0, 0


def main(upload_google_drive=True):
    # Start background memory monitor
    monitor = MemoryMonitor(interval=5.0)
    monitor.start()

    start_main = time.time()
    
    # Initialize variables that are used in finally block
    results = {}
    memory_stats = {}
    parallel_duration = 0
    run_successful = False

    try:
        run_migrations()

        logger.info("#" * 80)
        logger.info(f"Starting Data Collection Pipeline (Full Parallel Mode)")
        logger.info(f"Symbol selection mode: {SYMBOL_SELECTION['mode']}")

        enabled_rules = [rule for rule in OPTIONS_COLLECTION_RULES if rule.get("enabled", False)]
        logger.info(f"[INFO] Enabled collection rules: {len(enabled_rules)}")
        for rule in enabled_rules:
            logger.info(f"  - {rule['name']}: {rule['days_range']} days, {rule['frequency']}")

        if SYMBOL_SELECTION.get("use_max_limit", False) and "max_symbols" in SYMBOL_SELECTION:
            logger.info(f"[INFO] Symbol limit: {SYMBOL_SELECTION['max_symbols']}")

        logger.info(f"upload_df_google_drive: {upload_google_drive}\n")
        logger.info("#" * 80)

        # Prepare symbols and dates for option data
        expiry_date_strings = generate_expiry_dates_from_rules()
        symbols_to_use, filtered_expiry_dates = get_filtered_symbols_and_dates_with_logging(
            expiry_date_strings, "Option Data Collection"
        )
        
        load_option_chains()

        # All data collection tasks - run in parallel!
        parallel_tasks = [
            ("Yahoo Finance Analyst Price Targets", scrape_yahoo_finance_analyst_price_targets, ()),
            ("TradingView Option Data", scrape_option_data_trading_view, ()),
            ("Price & Technical Indicators", scrape_and_save_price_and_technical_indicators, ()),
            ("Dividend Radar", process_dividend_data, ()),
            ("Earning Dates", scrape_earning_dates, ()),
            ("Yahoo Query Option Chain", get_yahooquery_option_chain, ()),
            ("Yahoo Query Fundamentals", generate_fundamental_data, ()),
            ("Fetch Current Stock Prices", fetch_current_prices, ()),
        ]

        # Barchart scraping only on GitHub Actions
        if executed_as_github_action():
            logger.info("Running on GitHub Actions: Adding Barchart Data collection task")
            parallel_tasks.append(("Barchart Data", scrape_barchart, ()))
        else:
            logger.info("Not running on GitHub Actions: Skipping Barchart Data collection task")

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Running ALL {len(parallel_tasks)} data collection tasks in parallel")
        logger.info(f"Max workers: {len(parallel_tasks)}")
        logger.info(f"{'=' * 80}\n")

        parallel_start = time.time()

        # Use ThreadPoolExecutor for I/O-bound tasks (web scraping)
        # Set max_workers to number of tasks (they're all I/O bound)
        with ThreadPoolExecutor(max_workers=len(parallel_tasks)) as executor:
            future_to_task = {
                executor.submit(run_task_with_timing, name, func, *args): name
                for name, func, args in parallel_tasks
            }

            try:
                for future in as_completed(future_to_task):
                    task_name = future_to_task[future]
                    try:
                        result, error, mem_diff, peak_mem = future.result()
                        results[task_name] = (result, error)
                        memory_stats[task_name] = {"diff": mem_diff, "peak": peak_mem}
                    except Exception as e:
                        logger.error(f"Critical error in {task_name}: {e}")
                        results[task_name] = (None, e)
                        memory_stats[task_name] = {"diff": 0, "peak": 0}
            except KeyboardInterrupt:
                logger.warning("KeyboardInterrupt received! Shutting down executor...")
                executor.shutdown(wait=False, cancel_futures=True)
                raise

        parallel_duration = int(time.time() - parallel_start)
        logger.info(f"\n{'=' * 80}")
        logger.info(f"All parallel tasks completed in {parallel_duration}s")
        logger.info(f"All parallel tasks completed in {parallel_duration}s")
        logger.info(f"{'=' * 80}\n")

        # Historization
        run_historization_pipeline()

        # Upload (must be last)
        if upload_google_drive:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Uploading to Google Drive")
            logger.info(f"{'=' * 80}\n")
            run_task_with_timing(
                "Upload Database to Google Drive",
                upload_database
            )
        
        run_successful = True

    except Exception as e:
        # We catch exceptions to allow finally to run, but we want to re-raise them
        # if they imply a crash.
        logger.error(f"Critical failure in main pipeline: {e}")
        raise

    finally:
        # Summary
        end_main = time.time()
        total_duration = int(end_main - start_main)

        logger.info("\n" + "#" * 80)
        logger.info("DATA COLLECTION PIPELINE SUMMARY")
        logger.info("#" * 80)
        logger.info(f"Total Runtime: {total_duration}s ({total_duration / 60:.1f} minutes)")
        if parallel_duration > 0:
            logger.info(f"Parallel Execution: {parallel_duration}s")
            # We need to access parallel_tasks carefully as it might not be defined if crash happened before
            if 'parallel_tasks' in locals():
                logger.info(f"Time Saved: ~{(len(parallel_tasks) * 60 - parallel_duration)}s (estimated)")

        # Memory Summary
        logger.info("-" * 80)
        logger.info("MEMORY USAGE SUMMARY")
        logger.info("-" * 80)
        if memory_stats:
            # Sort by peak memory
            sorted_mem = sorted(memory_stats.items(), key=lambda x: x[1]['peak'], reverse=True)
            for task, stats in sorted_mem:
                logger.info(f"{task:<40} | Peak: {stats['peak']:6.2f} MB | Diff: {stats['diff']:+6.2f} MB")

            max_peak_task = sorted_mem[0]
            logger.info("-" * 80)
            logger.info(f"Highest Peak Memory: {max_peak_task[1]['peak']:.2f} MB ({max_peak_task[0]})")
        else:
            logger.info("No memory stats available.")

        # Check for failures
        failed_tasks = [name for name, (_, error) in results.items() if error is not None]
        
        if not run_successful:
            logger.warning(f"\n✗ Pipeline ABORTED/FAILED after {total_duration}s ({total_duration / 60:.1f} minutes)")
            if failed_tasks:
                 logger.warning(f"  Partial results with {len(failed_tasks)} failed tasks:")
                 for task in failed_tasks:
                    logger.warning(f"  - {task}")
        elif failed_tasks:
            logger.warning(f"\n⚠ Pipeline finished with {len(failed_tasks)} failures in {total_duration}s ({total_duration / 60:.1f} minutes):")
            for task in failed_tasks:
                logger.warning(f"  - {task}")
        else:
            logger.info(f"\n✓ All tasks completed successfully in {total_duration}s ({total_duration / 60:.1f} minutes)!")

        # Stop memory monitor
        monitor.stop()

        logger.info("#" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collection pipeline")
    parser.add_argument("--no-upload", action="store_true", help="Skip Google Drive upload")
    args = parser.parse_args()

    main(upload_google_drive=not args.no_upload)