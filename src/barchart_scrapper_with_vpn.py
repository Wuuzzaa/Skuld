"""
Barchart Scraper mit VPN-Unterstützung über SOCKS5 Proxy

Dieses Modul nutzt einen SSH-Tunnel zum Raspberry Pi (über WireGuard VPN)
um Barchart-Scraping mit Home-IP durchzuführen und IP-Blocking zu vermeiden.
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
    Scrapt Barchart-Daten mit VPN-Verbindung über SOCKS5 Proxy.
    
    WICHTIG: Barchart MUSS durch VPN (Raspberry Pi) gescrapt werden,
    sonst kommt es zu IP-Blocking von Barchart!
    
    Wenn VPN nicht funktioniert, wird das Scraping abgebrochen.
    """
    logger.info("=" * 80)
    logger.info("Starting Barchart scraping with VPN (SOCKS5)")
    logger.info("=" * 80)
    
    try:
        # VPN-Verbindung aufbauen
        with VPNManager() as vpn:
            if not vpn.is_connected:
                logger.error("❌ VPN connection failed - ABORTING Barchart scraping")
                logger.error("❌ Barchart MUST be scraped through VPN to avoid IP blocking!")
                logger.error("❌ Fix VPN setup before running Barchart scraper")
                return False
            
            logger.info("✅ VPN connected - proceeding with Barchart scraping")
            
            # Session mit Proxy holen
            session = vpn.get_session()
            
            # Barchart Scraper mit der Proxy-Session aufrufen
            from src.barchart_scrapper import scrape_barchart
            result = scrape_barchart(session=session)
            
            logger.info("✅ Barchart scraping completed successfully")
            return result
            
    except Exception as e:
        logger.error(f"❌ Error during Barchart scraping with VPN: {e}")
        logger.error("❌ Barchart scraping FAILED - data will be missing!")
        return False


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
