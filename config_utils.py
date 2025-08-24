from config import (
    GENERAL_TEST_MODE_ENABLED,
    MARRIED_PUT_TEST_MODE_ENABLED,
    MARRIED_PUT_EXTENDED_LEAPS_ENABLED,
    MARRIED_PUT_BASIC_LEAPS_ENABLED,
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