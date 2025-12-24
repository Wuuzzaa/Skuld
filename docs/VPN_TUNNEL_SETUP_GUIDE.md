# VPN Tunnel Setup Guide for Barchart Scraping

This guide documents how to set up a VPN tunnel using WireGuard and SSH to route traffic through a residential IP (e.g., a Raspberry Pi) to avoid IP blocking during scraping (specifically for Barchart).

## Architecture Overview

The setup consists of two layers:
1.  **WireGuard (Network Layer):** Establishes a secure private network between the Cloud Server (e.g., Hetzner) and the Home Server (Raspberry Pi).
2.  **SSH Tunnel (Application Layer):** The Python application creates a dynamic SSH tunnel (SOCKS5 proxy) over the WireGuard connection.

**Traffic Flow:**
`Python Scraper` -> `Local SOCKS5 Proxy (localhost:1080)` -> `SSH Tunnel` -> `WireGuard Interface` -> `Raspberry Pi` -> `Internet (Home IP)` -> `Target Website`

---

## 1. Python Implementation (`vpn_manager.py`)

This class manages the SSH tunnel lifecycle and provides a `requests.Session` configured to use the proxy.

```python
import subprocess
import time
import logging
import requests

logger = logging.getLogger(__name__)

class VPNManager:
    """Manages VPN connection via SSH SOCKS5 Proxy to Raspberry Pi"""
    
    def __init__(self, raspberry_host="raspberry-vpn", socks_port=1080):
        self.raspberry_host = raspberry_host
        self.socks_port = socks_port
        self.ssh_process = None
        self.is_connected = False
        self.proxies = None
    
    def start(self):
        """Starts SOCKS5 proxy via SSH to Raspberry Pi"""
        try:
            logger.info(f"🔐 VPN: Starting SOCKS5 proxy to {self.raspberry_host}:{self.socks_port}...")
            
            # Start SSH tunnel with SOCKS5 Proxy (-D)
            cmd = [
                'ssh', 
                '-N', # Do not execute a remote command
                '-D', f'127.0.0.1:{self.socks_port}', # SOCKS5 Proxy on localhost
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=10',
                '-o', 'ExitOnForwardFailure=yes',
                self.raspberry_host
            ]
            
            self.ssh_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            time.sleep(5) # Wait for tunnel to establish
            
            if self.ssh_process.poll() is not None:
                _, stderr = self.ssh_process.communicate()
                logger.error(f"❌ SSH Error: {stderr}")
                return False
            
            # Proxy config for requests (Important: socks5h for remote DNS resolution)
            self.proxies = {
                'http': f'socks5h://127.0.0.1:{self.socks_port}',
                'https': f'socks5h://127.0.0.1:{self.socks_port}'
            }
            
            # Verify IP
            try:
                ip = requests.get('https://api.ipify.org', proxies=self.proxies, timeout=10).text
                logger.info(f"✅ VPN ACTIVE! Public IP: {ip}")
                self.is_connected = True
                return True
            except Exception as e:
                logger.error(f"❌ VPN IP Check failed: {e}")
                self.stop()
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting proxy: {e}")
            return False
    
    def stop(self):
        if self.ssh_process:
            self.ssh_process.terminate()
            self.ssh_process.wait(timeout=5)
        self.is_connected = False
        self.proxies = None
        logger.info("🔓 VPN: Proxy stopped")

    def get_session(self):
        """Returns a requests.Session configured to use the tunnel"""
        if not self.is_connected:
            raise RuntimeError("VPN not connected")
        session = requests.Session()
        session.proxies.update(self.proxies)
        return session
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
```

---

## 2. Docker Configuration

The container needs `openssh-client` and access to the host's SSH keys.

**Dockerfile:**
```dockerfile
# ...
# Install SSH client
RUN apt-get update && apt-get install -y openssh-client procps
# ...
```

**docker-compose.yml:**
Mount the host's SSH directory into the container.
```yaml
services:
  app:
    # ...
    volumes:
      # Mount SSH keys from host to container (read-only)
      - /home/deploy/.ssh:/root/.ssh:ro
```

---

## 3. Server & SSH Configuration (Host Side)

On the host machine (Cloud Server), configure SSH access to the Raspberry Pi.

1.  **Generate SSH Key (on Host):**
    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vpn -N ""
    ```

2.  **Copy Key to Raspberry Pi:**
    ```bash
    ssh-copy-id -i ~/.ssh/id_ed25519_vpn.pub pi@10.0.0.1
    # (Replace 10.0.0.1 with the WireGuard IP of the Raspberry Pi)
    ```

3.  **Create SSH Config (`~/.ssh/config` on Host):**
    This simplifies the connection command in Python.
    ```ssh
    Host raspberry-vpn
        HostName 10.0.0.1
        User pi
        IdentityFile ~/.ssh/id_ed25519_vpn
        StrictHostKeyChecking no
        UserKnownHostsFile=/dev/null
    ```

---

## 4. Usage Example

How to use the `VPNManager` in your scraping code:

```python
from vpn_manager import VPNManager

def scrape_data_with_vpn():
    # Context Manager handles start/stop of the tunnel
    with VPNManager() as vpn:
        if not vpn.is_connected:
            print("VPN connection failed!")
            return
            
        # Get session with proxy configuration
        session = vpn.get_session()
        
        # Use session for requests - traffic is routed through Raspberry Pi
        try:
            response = session.get("https://www.barchart.com/...")
            print(f"Status: {response.status_code}")
            # Process data...
        except Exception as e:
            print(f"Request failed: {e}")
```
