"""
Configuration loader for YT-DLP Local Service.
Reads from environment variables and .env file.
"""
import os
from pathlib import Path

# Load .env file if present
def load_env_file():
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key not in os.environ:  # Don't override existing env vars
                        os.environ[key] = value

load_env_file()

# Base directory
BASE_DIR = Path(__file__).parent.resolve()

# Server configuration
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '5000'))

# Storage paths
DOWNLOAD_DIR = Path(os.environ.get('DOWNLOAD_DIR', str(BASE_DIR / 'downloads'))).resolve()
LOG_DIR = Path(os.environ.get('LOG_DIR', str(BASE_DIR / 'logs'))).resolve()

# Ensure directories exist
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Cookie files (optional)
YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')
INSTAGRAM_COOKIES = os.environ.get('INSTAGRAM_COOKIES', '')
TIKTOK_COOKIES = os.environ.get('TIKTOK_COOKIES', '')

# Resolve cookie paths relative to BASE_DIR if not absolute
def resolve_cookie_path(cookie_path: str) -> str:
    if not cookie_path:
        return ''
    p = Path(cookie_path)
    if not p.is_absolute():
        p = BASE_DIR / p
    if p.exists():
        return str(p.resolve())
    return ''

YOUTUBE_COOKIES = resolve_cookie_path(YOUTUBE_COOKIES)
INSTAGRAM_COOKIES = resolve_cookie_path(INSTAGRAM_COOKIES)
TIKTOK_COOKIES = resolve_cookie_path(TIKTOK_COOKIES)

# Proxy configuration (Decodo sticky mobile proxies)
PROXY_HOST = os.environ.get('PROXY_HOST', '')
PROXY_USER = os.environ.get('PROXY_USER', '')
PROXY_PASS = os.environ.get('PROXY_PASS', '')

# Sticky proxy port per platform (each gets its own session)
PROXY_PORTS = {
    'youtube': int(os.environ.get('PROXY_PORT_YOUTUBE', '10001')),
    'instagram': int(os.environ.get('PROXY_PORT_INSTAGRAM', '10002')),
    'tiktok': int(os.environ.get('PROXY_PORT_TIKTOK', '10003')),
    'twitter': int(os.environ.get('PROXY_PORT_TWITTER', '10004')),
    'facebook': int(os.environ.get('PROXY_PORT_FACEBOOK', '10005')),
    'default': int(os.environ.get('PROXY_PORT_DEFAULT', '10006')),
}

def get_proxy_url(platform: str) -> str:
    """Get the proxy URL for a specific platform."""
    if not PROXY_HOST or not PROXY_USER or not PROXY_PASS:
        return ''
    port = PROXY_PORTS.get(platform, PROXY_PORTS['default'])
    return f'http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{port}'

# Version
VERSION = '1.1.0'
