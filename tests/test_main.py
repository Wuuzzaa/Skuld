from main import main


def test_main_runs_completely():
    """
    This test runs on the first 3 Symbols and the first 3 Expiration dates.
    """
    assert main(testmode=True) is None



