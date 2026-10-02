"""
YT-DLP Local Service
A simplified local video extraction and download service.
"""
from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import re
import ssl
import time
import copy
import json
import shutil
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from functools import wraps

import config


# ============================================================================
# Retry Logic for Transient Failures
# ============================================================================

# Transient error patterns that warrant automatic retry
TRANSIENT_ERROR_PATTERNS = [
    'RECORD_LAYER_FAILURE',
    'SSL',
    'ssl',
    'Connection reset',
    'connection reset',
    'Connection refused',
    'Connection timed out',
    'timed out',
    'Temporary failure in name resolution',
    'Name or service not known',
    'Network is unreachable',
    'EOF occurred',
    'RemoteDisconnected',
    'IncompleteRead',
    'ConnectionError',
    'ProxyError',
    'SOCKS',
    'tunnel connection failed',
    'urlopen error',
    'HTTPSConnectionPool',
]

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds

# Relative template so yt-dlp paths.home is honored (absolute -o disables it).
# playlist_index is empty for a single video and set for carousel/story entries.
OUTTMPL = '%(title).80S [%(id)s] %(playlist_index|)s.%(ext)s'

# Web is the extractor default (InstagramBaseIE._APP_IDS['web']).
INSTAGRAM_WEB_APP_ID = 'web'
INSTAGRAM_IOS_APP_ID = 'ios'

# Login wall / empty media from the 2026.08.19 Instagram extractor.
IG_WALL_MARKERS = (
    'empty media',
    'login page',
    'login required',
    'no longer valid',
    'need to log in',
    'locked behind',
)

IG_PRIVATE_FALLBACK_MARKERS = (
    'login required',
    'empty media',
    'private',
    'rate-limit',
    'not available',
    'login page',
    'no longer valid',
    'need to log in',
)

MEDIA_SUFFIXES = {
    '.mp4', '.mkv', '.webm', '.m4a', '.mp3', '.opus', '.ogg', '.mov',
    '.m4v', '.aac', '.flac', '.wav',
}

# Instagram private API host + web app id used by the existing fallback.
# X-ASBD-ID matches yt-dlp 2026.08.19 InstagramBaseIE._api_headers.
IG_PRIVATE_APP_ID = '936619743392459'
IG_ASBD_ID = '359341'


class ClientInputError(Exception):
    """Caller passed a URL this service will not send to the extractor."""


def is_transient_error(error_msg: str) -> bool:
    """Check if an error message indicates a transient/retryable failure."""
    return any(pattern in error_msg for pattern in TRANSIENT_ERROR_PATTERNS)


def retry_on_transient(func):
    """Decorator that retries a function on transient network/SSL errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (yt_dlp.utils.DownloadError, ssl.SSLError, OSError, ConnectionError) as e:
                error_msg = str(e)
                last_error = e
                if attempt < MAX_RETRIES and is_transient_error(error_msg):
                    wait = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Transient error on attempt {attempt}/{MAX_RETRIES}: {error_msg[:200]}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:
                error_msg = str(e)
                last_error = e
                if attempt < MAX_RETRIES and is_transient_error(error_msg):
                    wait = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Transient error on attempt {attempt}/{MAX_RETRIES}: {error_msg[:200]}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    continue
                raise
        raise last_error
    return wrapper
