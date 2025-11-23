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
    
    def __init__(self, raspberry_host="pi@10.0.0.1", socks_port=1080):
        """
        Args:
            raspberry_host: SSH-Host (pi@10.0.0.1 oder aus ~/.ssh/config)
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
            logger.info("=" * 80)
            logger.info(f"🔐 VPN: Starte SOCKS5-Proxy zu {self.raspberry_host}:{self.socks_port}...")
            logger.info("=" * 80)
            
            # SSH-Tunnel mit SOCKS5 Proxy starten
            # -f: Background, -N: Kein Remote Command, -D: SOCKS5 Proxy
            # -o StrictHostKeyChecking=no: Keine Hostkey-Prüfung
            self.ssh_process = subprocess.Popen(
                ['ssh', '-f', '-N', '-D', f'127.0.0.1:{self.socks_port}',
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 self.raspberry_host],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            logger.info("🔄 VPN: Warte auf SSH-Tunnel...")
            # Kurz warten bis Tunnel steht
            time.sleep(3)
            
            # Proxy-Config für requests
            self.proxies = {
                'http': f'socks5h://127.0.0.1:{self.socks_port}',
                'https': f'socks5h://127.0.0.1:{self.socks_port}'
            }
            
            # IP prüfen über Proxy
            try:
                logger.info("🔍 VPN: Prüfe öffentliche IP über VPN-Tunnel...")
                response = requests.get('https://api.ipify.org', 
                                        proxies=self.proxies, 
                                        timeout=10)
                ip = response.text
                logger.info("=" * 80)
                logger.info(f"✅ VPN AKTIV! Öffentliche IP: {ip}")
                logger.info(f"✅ VPN: Traffic läuft jetzt über Raspberry Pi / Home-Netzwerk")
                logger.info("=" * 80)
                self.is_connected = True
                return True
            except Exception as e:
                logger.error("=" * 80)
                logger.error(f"❌ VPN: IP-Check fehlgeschlagen: {e}")
                logger.error("❌ VPN: SSH-Tunnel läuft, aber kein Internet-Zugriff")
                logger.error("=" * 80)
                self.stop()
                return False
                
        except Exception as e:
            logger.error(f"❌ Fehler beim Proxy-Start: {e}")
            self.is_connected = False
            return False
    
    def stop(self):
        """SOCKS5-Proxy beenden"""
        try:
            logger.info("=" * 80)
            logger.info("🔓 VPN: Beende SOCKS5-Proxy...")
            
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
            logger.info("✅ VPN: Proxy beendet - zurück zu normaler Hetzner-IP")
            logger.info("=" * 80)
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
