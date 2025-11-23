#!/usr/bin/env python3
"""
VPN Manager für WireGuard über SOCKS5 Proxy
Verwaltet SSH-Tunnel zum Raspberry Pi für Barchart Scraping
"""
import subprocess
import time
import logging
import requests
import socket

logger = logging.getLogger(__name__)


class VPNManager:
    """Verwaltet VPN-Verbindung über SSH SOCKS5 Proxy zum Raspberry Pi"""
    
    def __init__(self, raspberry_host="raspberry-vpn", socks_port=1080):
        """
        Args:
            raspberry_host: SSH-Host (aus ~/.ssh/config) oder pi@10.0.0.1
            socks_port: Port für SOCKS5 Proxy (default 1080)
        """
        self.raspberry_host = raspberry_host
        self.socks_port = socks_port
        self.ssh_process = None
        self.is_connected = False
        self.proxies = None
    
    def start(self):
        """SOCKS5-Proxy über SSH zum Raspberry Pi aufbauen"""
        try:
            logger.info(f"🔐 Starte SOCKS5-Proxy zu {self.raspberry_host}:{self.socks_port}...")
            
            # SSH-Tunnel mit SOCKS5 Proxy starten
            # -f: Background, -N: Kein Remote Command, -D: SOCKS5 Proxy
            self.ssh_process = subprocess.Popen(
                ['ssh', '-f', '-N', '-D', f'127.0.0.1:{self.socks_port}', 
                 self.raspberry_host],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Kurz warten bis Tunnel steht
            time.sleep(3)
            
            # Proxy-Config für requests
            self.proxies = {
                'http': f'socks5h://127.0.0.1:{self.socks_port}',
                'https': f'socks5h://127.0.0.1:{self.socks_port}'
            }
            
            # IP prüfen über Proxy
            try:
                response = requests.get('https://api.ipify.org', 
                                        proxies=self.proxies, 
                                        timeout=10)
                ip = response.text
                logger.info(f"✅ SOCKS5-Proxy aktiv. Öffentliche IP: {ip}")
                self.is_connected = True
                return True
            except Exception as e:
                logger.error(f"❌ IP-Check fehlgeschlagen: {e}")
                self.stop()
                return False
                
        except Exception as e:
            logger.error(f"❌ Fehler beim Proxy-Start: {e}")
            self.is_connected = False
            return False
    
    def stop(self):
        """SOCKS5-Proxy beenden"""
        try:
            logger.info("🔓 Beende SOCKS5-Proxy...")
            
            # SSH-Prozess beenden
            if self.ssh_process:
                self.ssh_process.terminate()
                self.ssh_process.wait(timeout=5)
            
            # Alle SSH-Tunnel-Prozesse killen (Fallback)
            subprocess.run(['pkill', '-f', f'ssh.*{self.raspberry_host}'], 
                          check=False, 
                          capture_output=True)
            
            self.is_connected = False
            self.proxies = None
            logger.info("✅ Proxy beendet")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Proxy-Stop: {e}")
            return False
    
    def get_session(self):
        """
        Gibt eine requests.Session mit konfiguriertem Proxy zurück
        
        Returns:
            requests.Session mit Proxy-Konfiguration
        """
        if not self.is_connected or not self.proxies:
            raise RuntimeError("VPN nicht verbunden - rufe zuerst start() auf")
        
        session = requests.Session()
        session.proxies.update(self.proxies)
        return session
    
    def __enter__(self):
        """Context Manager: Proxy beim Eintreten starten"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager: Proxy beim Verlassen beenden"""
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
