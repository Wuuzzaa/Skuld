from config import (
    GENERAL_TEST_MODE_ENABLED,
    MARRIED_PUT_TEST_MODE_ENABLED,
    MARRIED_PUT_TEST_MODE_MAX_SYMBOLS,
    MARRIED_PUT_EXTENDED_LEAPS_ENABLED,
    MARRIED_PUT_BASIC_LEAPS_ENABLED,
    SYMBOLS,
    SYMBOLS_EXCHANGE,
    GENERAL_TEST_MODE_MAX_SYMBOLS,
)

def validate_config():
    """Validate configuration and show active mode"""
    if GENERAL_TEST_MODE_ENABLED and MARRIED_PUT_TEST_MODE_ENABLED:
        raise ValueError("GENERAL_TEST_MODE and MARRIED_PUT_TEST_MODE cannot be enabled simultaneously")
    
    if GENERAL_TEST_MODE_ENABLED:
        return "GENERAL_TEST_MODE"
    elif MARRIED_PUT_TEST_MODE_ENABLED:
        return "MARRIED_PUT_TEST_MODE"
    elif MARRIED_PUT_EXTENDED_LEAPS_ENABLED:
        return "EXTENDED_LEAPS_MODE"
    elif MARRIED_PUT_BASIC_LEAPS_ENABLED:
        return "BASIC_LEAPS_MODE"
    else:
        return "STANDARD_OPTIONS_ONLY"


def get_filtered_symbols_with_logging(context_name="Processing"):
    """
    Centralized symbol filtering based on active configuration mode.
    
    Args:
        context_name (str): Context for logging (e.g., "Yahoo Finance Scraping")
    
    Returns:
        tuple: (symbols_list, active_mode)
    """
    active_mode = validate_config()
    
    if active_mode == "GENERAL_TEST_MODE":
        symbols = SYMBOLS[:GENERAL_TEST_MODE_MAX_SYMBOLS]
        print(f"[TESTMODE] Only {GENERAL_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
    elif active_mode == "MARRIED_PUT_TEST_MODE":
        if MARRIED_PUT_TEST_MODE_MAX_SYMBOLS is not None:
            symbols = SYMBOLS[:MARRIED_PUT_TEST_MODE_MAX_SYMBOLS]
            print(f"[MARRIED_PUT_TEST_MODE] Only {MARRIED_PUT_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
        else:
            symbols = SYMBOLS
            print(f"[MARRIED_PUT_TEST_MODE] All {len(SYMBOLS)} symbols will be processed.")
    else:
        symbols = SYMBOLS
        print(f"[PRODUCTION] All {len(SYMBOLS)} symbols will be processed.")
    
    return symbols, active_mode