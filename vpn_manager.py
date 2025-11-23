#!/usr/bin/env python3
"""
VPN Manager für WireGuard
Verwaltet VPN-Verbindung für Barchart Scraping
"""
import subprocess
import time
import logging
import requests

logger = logging.getLogger(__name__)


class VPNManager:
    """Verwaltet WireGuard VPN-Verbindungen"""
    
    def __init__(self, interface="wg0"):
        self.interface = interface
        self.is_connected = False
    
    def start(self):
        """VPN-Verbindung aufbauen"""
        try:
            logger.info("🔐 Starte VPN-Verbindung...")
            subprocess.run(['wg-quick', 'up', self.interface], check=True, capture_output=True)
            time.sleep(5)  # Warten bis VPN steht
            
            # IP prüfen
            try:
                response = requests.get('https://api.ipify.org', timeout=10)
                ip = response.text
                logger.info(f"✅ VPN aktiv. Öffentliche IP: {ip}")
                self.is_connected = True
                return True
            except Exception as e:
                logger.warning(f"Konnte öffentliche IP nicht prüfen: {e}")
                self.is_connected = True
                return True
                
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ VPN-Start fehlgeschlagen: {e.stderr.decode()}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"❌ Unerwarteter Fehler beim VPN-Start: {e}")
            self.is_connected = False
            return False
    
    def stop(self):
        """VPN-Verbindung beenden"""
        try:
            logger.info("🔓 Beende VPN-Verbindung...")
            subprocess.run(['wg-quick', 'down', self.interface], check=False, capture_output=True)
            self.is_connected = False
            logger.info("✅ VPN beendet")
            return True
        except Exception as e:
            logger.error(f"Fehler beim VPN-Stop: {e}")
            return False
    
    def status(self):
        """VPN-Status abfragen"""
        try:
            result = subprocess.run(['wg', 'show', self.interface], 
                                    check=True, 
                                    capture_output=True, 
                                    text=True)
            return result.stdout
        except subprocess.CalledProcessError:
            return None
    
    def __enter__(self):
        """Context Manager: VPN beim Eintreten starten"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager: VPN beim Verlassen beenden"""
        self.stop()


# Beispiel-Verwendung
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Mit Context Manager (empfohlen)
    with VPNManager() as vpn:
        if vpn.is_connected:
            print("VPN ist aktiv!")
            print(vpn.status())
            # Hier dein Scraping-Code
            time.sleep(5)
    
    print("VPN wurde automatisch beendet")
