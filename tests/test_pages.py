import pytest
from streamlit.testing.v1 import AppTest
from pathlib import Path

#todo main testen. mit subset der symbole und ohne db upload

# Alle Page-Dateien die getestet werden sollen
PAGES = [
    "pages/analyst_prices.py",
    "pages/spreads.py",
    "pages/iron_condors.py",
    "pages/married_put_analysis.py",
    "pages/position_insurance_tool.py",
    "pages/multifactor_swingtrading.py",
    "pages/sector_rotation.py",
    "pages/expected_value.py",
    "pages/data_change_logs.py",
    "pages/symbolpage.py"
]


@pytest.mark.parametrize("page_file", PAGES)
def test_page_runs_without_error(page_file):
    """Test that each page runs without errors"""
    page_path = Path(page_file)

    # Prüfe ob Datei existiert
    assert page_path.exists(), f"Page {page_file} nicht gefunden"

    # Führe die Page aus
    at = AppTest.from_file(str(page_path))
    timeout = 60 if "sector_rotation" in page_file else 30
    at.run(timeout=timeout)

    # Prüfe ob es Fehler gibt
    assert not at.exception, f"Fehler in {page_file}: {at.exception}"
    print(f"✓ {page_file} durchgelaufen ohne Fehler")


def test_all_pages_exist():
    """Verify all page files exist"""
    for page_file in PAGES:
        assert Path(page_file).exists(), f"{page_file} existiert nicht"