"""
Barchart Scraper mit VPN-Unterstützung

Dieses Modul zeigt, wie der Barchart Scraper mit VPN genutzt werden kann.
Verwende dies als Vorlage, um die VPN-Funktionalität in deinen bestehenden
Barchart Scraper zu integrieren.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from vpn_manager import VPNManager
from src.logger_config import setup_logging
import logging

# Setup logging
logger = logging.getLogger(__name__)


def scrape_barchart_with_vpn():
    """
    Scrapt Barchart-Daten mit VPN-Verbindung.
    
    Die VPN-Verbindung wird automatisch aufgebaut und nach dem Scraping
    wieder beendet, sodass bei jedem Lauf eine neue Home-IP verwendet wird.
    """
    logger.info("=" * 80)
    logger.info("Starting Barchart scraping with VPN")
    logger.info("=" * 80)
    
    try:
        # VPN-Verbindung aufbauen
        with VPNManager() as vpn:
            if not vpn.is_connected:
                logger.error("❌ VPN connection failed - aborting Barchart scraping")
                return False
            
            logger.info("✅ VPN connected - proceeding with Barchart scraping")
            
            # Hier den eigentlichen Barchart Scraper aufrufen
            from src.barchart_scrapper import scrape_barchart
            result = scrape_barchart()
            
            logger.info("✅ Barchart scraping completed successfully")
            return result
            
    except Exception as e:
        logger.error(f"❌ Error during Barchart scraping with VPN: {e}")
        return False
    
    finally:
        logger.info("VPN connection closed")


def main():
    """Test-Funktion für lokale Entwicklung"""
    setup_logging(log_level=logging.INFO, console_output=True)
    
    result = scrape_barchart_with_vpn()
    
    if result:
        print("✅ Barchart scraping mit VPN erfolgreich!")
    else:
        print("❌ Barchart scraping mit VPN fehlgeschlagen")


if __name__ == "__main__":
    main()
