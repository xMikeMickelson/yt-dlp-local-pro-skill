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
import logging
from pathlib import Path
from datetime import datetime
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

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_DIR / 'yt-dlp-local.log')
    ]
)
logger = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    """Detect the platform from URL."""
    url_lower = url.lower()
    if any(d in url_lower for d in ['instagram.com', 'instagr.am']):
        return 'instagram'
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    elif any(d in url_lower for d in ['twitter.com', 'x.com']):
        return 'twitter'
    elif any(d in url_lower for d in ['facebook.com', 'fb.com', 'fb.watch']):
        return 'facebook'
    else:
        return 'youtube'


def sanitize_filename(title: str) -> str:
    """Sanitize title for use as filename."""
    # Remove/replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('._')
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized or 'video'


def get_video_id(info: dict) -> str:
    """Extract video ID from info dict."""
    return info.get('id') or info.get('display_id') or 'unknown'


def get_ydl_opts(platform: str, audio_only: bool = False, download: bool = False,
                 output_path: str = None, quality: str = 'best') -> dict:
    """Build yt-dlp options based on platform and requirements."""

    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }

    # Add cookies if available
    # Instagram: use a COPY of the master cookie file because yt-dlp rewrites
    # the cookie file after each request and strips the sessionid cookie
    if platform == 'youtube' and config.YOUTUBE_COOKIES:
        opts['cookiefile'] = config.YOUTUBE_COOKIES
        logger.info(f"Using YouTube cookies: {config.YOUTUBE_COOKIES}")
    elif platform == 'instagram' and config.INSTAGRAM_COOKIES:
        import shutil
        import tempfile
        master_cookies = config.INSTAGRAM_COOKIES.replace('.txt', '_master.txt')
        if os.path.exists(master_cookies):
            # Copy master to a temp file so yt-dlp doesn't corrupt the original
            tmp_cookie = os.path.join(os.path.dirname(master_cookies), 'instagram_tmp.txt')
            shutil.copy2(master_cookies, tmp_cookie)
            opts['cookiefile'] = tmp_cookie
            logger.info(f"Using Instagram cookies (from master): {master_cookies}")
        else:
            opts['cookiefile'] = config.INSTAGRAM_COOKIES
            logger.info(f"Using Instagram cookies: {config.INSTAGRAM_COOKIES}")
    elif platform == 'tiktok' and config.TIKTOK_COOKIES:
        opts['cookiefile'] = config.TIKTOK_COOKIES
        logger.info(f"Using TikTok cookies: {config.TIKTOK_COOKIES}")

    # Add proxy (sticky per platform)
    proxy_url = config.get_proxy_url(platform)
    if proxy_url:
        opts['proxy'] = proxy_url
        logger.info(f"Using proxy for {platform}: {config.PROXY_HOST}:{config.PROXY_PORTS.get(platform, config.PROXY_PORTS['default'])}")

    # Instagram-specific: add extractor args for better private content support
    if platform == 'instagram':
        # Use the web app ID (default) for authenticated requests
        # The mobile app ID (124024574287414) gives different formats but can be flaky
        opts.setdefault('extractor_args', {})
        opts['extractor_args']['instagram'] = ['app_id=936619743392459']
        # Add proper headers to avoid rate limiting
        opts.setdefault('http_headers', {})
        opts['http_headers'].update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Site': 'same-origin',
        })

    if not download:
        opts['skip_download'] = True
        return opts

    # Download options
    if output_path:
        opts['outtmpl'] = output_path

    # Format selection
    if audio_only:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }]
    else:
        # Video format based on quality
        if quality == 'best':
            if platform in ['instagram', 'tiktok', 'twitter', 'facebook']:
                opts['format'] = 'best'
            else:
                # YouTube: prefer separate streams for highest quality
                opts['format'] = 'bestvideo+bestaudio/best'
        elif quality == 'worst':
            opts['format'] = 'worst'
        elif quality.isdigit():
            height = quality
            if platform in ['instagram', 'tiktok', 'twitter', 'facebook']:
                opts['format'] = f'best[height<={height}]/best'
            else:
                opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
        else:
            opts['format'] = 'best'

    # Merge format for YouTube (needs ffmpeg)
    if platform == 'youtube' and not audio_only:
        opts['merge_output_format'] = 'mp4'

    return opts


@retry_on_transient
def extract_info(url: str) -> dict:
    """Extract video information without downloading."""
    platform = detect_platform(url)
    opts = get_ydl_opts(platform, download=False)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return info, platform


@retry_on_transient
def download_video(url: str, opts: dict) -> None:
    """Download a video with retry logic for transient failures."""
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        'service': 'yt-dlp-local',
        'version': config.VERSION,
        'endpoints': ['/health', '/api/extract', '/api/download', '/api/audio', '/api/formats']
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'version': config.VERSION,
        'download_dir': str(config.DOWNLOAD_DIR),
        'cookies': {
            'youtube': bool(config.YOUTUBE_COOKIES),
            'instagram': bool(config.INSTAGRAM_COOKIES),
            'tiktok': bool(config.TIKTOK_COOKIES)
        },
        'proxy': {
            'enabled': bool(config.PROXY_HOST),
            'host': config.PROXY_HOST or None,
            'ports': config.PROXY_PORTS if config.PROXY_HOST else None
        }
    })


@app.route('/api/extract', methods=['POST'])
def api_extract():
    """Extract video metadata without downloading."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Extracting metadata: {url}")

    try:
        info, platform = extract_info(url)

        # Get available resolutions
        formats = info.get('formats') or []
        resolutions = set()
        for f in formats:
            if f and f.get('height'):
                resolutions.add(f"{f['height']}p")
        if any(f.get('acodec') and f.get('acodec') != 'none' for f in formats if f):
            resolutions.add('audio-only')

        response = {
            'success': True,
            'platform': platform,
            'id': get_video_id(info),
            'title': info.get('title'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader') or info.get('channel'),
            'upload_date': info.get('upload_date'),
            'view_count': info.get('view_count'),
            'description': info.get('description', '')[:500] if info.get('description') else None,
            'formats_available': sorted(list(resolutions), key=lambda x: (x != 'audio-only', x), reverse=True)
        }

        logger.info(f"Extracted: {info.get('title')} ({platform})")
        return jsonify(response)

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Extraction failed: {error_msg}")
        return jsonify({'error': 'Download error', 'message': error_msg}), 400
    except Exception as e:
        logger.exception(f"Extraction failed: {e}")
        return jsonify({'error': 'Extraction failed', 'message': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    """Download video to local storage."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    quality = data.get('quality', 'best')
    audio_only = data.get('audio_only', False)

    logger.info(f"Downloading: {url} (quality={quality}, audio_only={audio_only})")

    try:
        # First extract info to get title and ID
        info, platform = extract_info(url)

        video_id = get_video_id(info)
        title = sanitize_filename(info.get('title', 'video'))

        # Create platform subdirectory
        platform_dir = config.DOWNLOAD_DIR / platform
        platform_dir.mkdir(exist_ok=True)

        # Build output path
        ext = 'm4a' if audio_only else 'mp4'
        filename = f"{title}-{video_id}.{ext}"
        output_path = platform_dir / filename

        # If file exists, add timestamp
        if output_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{title}-{video_id}-{timestamp}.{ext}"
            output_path = platform_dir / filename

        # Download
        opts = get_ydl_opts(
            platform,
            audio_only=audio_only,
            download=True,
            output_path=str(platform_dir / f"{title}-{video_id}.%(ext)s"),
            quality=quality
        )

        download_video(url, opts)

        # Find the downloaded file (extension might differ)
        downloaded_files = list(platform_dir.glob(f"{title}-{video_id}.*"))
        if not downloaded_files:
            raise Exception("Download completed but file not found")

        # Get the most recent file
        actual_file = max(downloaded_files, key=lambda p: p.stat().st_mtime)
        file_size = actual_file.stat().st_size / (1024 * 1024)  # MB

        response = {
            'success': True,
            'platform': platform,
            'title': info.get('title'),
            'file_path': str(actual_file),
            'file_name': actual_file.name,
            'file_size_mb': round(file_size, 2),
            'duration': info.get('duration'),
            'ext': actual_file.suffix.lstrip('.')
        }

        logger.info(f"Downloaded: {actual_file.name} ({file_size:.2f} MB)")
        return jsonify(response)

    except (yt_dlp.utils.DownloadError, Exception) as e:
        error_msg = str(e)
        logger.error(f"Download failed: {error_msg}")

        # Auto-fallback for Instagram private content
        if detect_platform(url) == 'instagram' and any(kw in error_msg.lower() for kw in
                ['login required', 'empty media', 'private', 'rate-limit', 'not available']):
            logger.info("Attempting Instagram private API fallback...")
            try:
                with app.test_request_context(json={'url': url, 'quality': quality}):
                    return api_instagram_private()
            except Exception as fallback_err:
                logger.error(f"Instagram fallback also failed: {fallback_err}")

        return jsonify({'error': 'Download error', 'message': error_msg}), 400


@app.route('/api/audio', methods=['POST'])
def api_audio():
    """Extract audio only - convenience endpoint."""
    data = request.json or {}
    data['audio_only'] = True

    # Reuse download endpoint
    with app.test_request_context(json=data):
        request.json  # Ensure json is loaded

    # Call download with audio_only=True
    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Extracting audio: {url}")

    try:
        info, platform = extract_info(url)

        video_id = get_video_id(info)
        title = sanitize_filename(info.get('title', 'audio'))

        platform_dir = config.DOWNLOAD_DIR / platform
        platform_dir.mkdir(exist_ok=True)

        opts = get_ydl_opts(
            platform,
            audio_only=True,
            download=True,
            output_path=str(platform_dir / f"{title}-{video_id}.%(ext)s"),
            quality='best'
        )

        download_video(url, opts)

        # Find the downloaded file
        downloaded_files = list(platform_dir.glob(f"{title}-{video_id}.*"))
        if not downloaded_files:
            raise Exception("Audio extraction completed but file not found")

        actual_file = max(downloaded_files, key=lambda p: p.stat().st_mtime)
        file_size = actual_file.stat().st_size / (1024 * 1024)

        response = {
            'success': True,
            'platform': platform,
            'title': info.get('title'),
            'file_path': str(actual_file),
            'file_name': actual_file.name,
            'file_size_mb': round(file_size, 2),
            'duration': info.get('duration'),
            'ext': actual_file.suffix.lstrip('.')
        }

        logger.info(f"Audio extracted: {actual_file.name} ({file_size:.2f} MB)")
        return jsonify(response)

    except Exception as e:
        logger.exception(f"Audio extraction failed: {e}")
        return jsonify({'error': 'Audio extraction failed', 'message': str(e)}), 500


@app.route('/api/formats', methods=['POST'])
def api_formats():
    """List available formats for a URL."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Listing formats: {url}")

    try:
        info, platform = extract_info(url)

        formats = []
        for f in (info.get('formats') or []):
            if not f:
                continue

            format_info = {
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'resolution': f"{f.get('height', '?')}p" if f.get('height') else 'audio',
                'width': f.get('width'),
                'height': f.get('height'),
                'fps': f.get('fps'),
                'vcodec': f.get('vcodec'),
                'acodec': f.get('acodec'),
                'filesize_mb': round(f.get('filesize', 0) / (1024 * 1024), 2) if f.get('filesize') else None,
                'tbr': f.get('tbr'),  # Total bitrate
            }
            formats.append(format_info)

        return jsonify({
            'success': True,
            'platform': platform,
            'title': info.get('title'),
            'formats': formats
        })

    except Exception as e:
        logger.exception(f"Format listing failed: {e}")
        return jsonify({'error': 'Failed to list formats', 'message': str(e)}), 500


@app.route('/api/instagram/private', methods=['POST'])
def api_instagram_private():
    """Download Instagram content that requires authentication (private accounts, stories).
    Uses Instagram's private API directly as a fallback when yt-dlp's extractor fails.
    """
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Instagram private download: {url}")

    # First try the normal yt-dlp path (with cookies it should handle most cases)
    try:
        info, platform = extract_info(url)
        if platform != 'instagram':
            return jsonify({'error': 'Not an Instagram URL'}), 400

        # If extract_info succeeded, the content is accessible - just download it
        video_id = get_video_id(info)
        title = sanitize_filename(info.get('title', 'video'))
        platform_dir = config.DOWNLOAD_DIR / 'instagram'
        platform_dir.mkdir(exist_ok=True)

        opts = get_ydl_opts(
            'instagram',
            download=True,
            output_path=str(platform_dir / f"{title}-{video_id}.%(ext)s"),
            quality=data.get('quality', 'best')
        )

        download_video(url, opts)

        downloaded_files = list(platform_dir.glob(f"{title}-{video_id}.*"))
        if not downloaded_files:
            raise Exception("Download completed but file not found")

        actual_file = max(downloaded_files, key=lambda p: p.stat().st_mtime)
        file_size = actual_file.stat().st_size / (1024 * 1024)

        return jsonify({
            'success': True,
            'method': 'yt-dlp-authenticated',
            'platform': 'instagram',
            'title': info.get('title'),
            'file_path': str(actual_file),
            'file_name': actual_file.name,
            'file_size_mb': round(file_size, 2),
            'duration': info.get('duration'),
            'ext': actual_file.suffix.lstrip('.')
        })

    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Standard yt-dlp failed for private content: {error_msg}")

        # Fallback: try direct Instagram GraphQL API
        try:
            import urllib.request
            import json as json_mod

            # Extract shortcode from URL
            shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if not shortcode_match:
                return jsonify({'error': 'Cannot extract shortcode from URL', 'yt_dlp_error': error_msg}), 400

            shortcode = shortcode_match.group(1)

            # Load cookies for the request (prefer master file)
            cookie_str = ''
            master_path = config.INSTAGRAM_COOKIES.replace('.txt', '_master.txt') if config.INSTAGRAM_COOKIES else ''
            cookie_file = master_path if os.path.exists(master_path) else config.INSTAGRAM_COOKIES
            if cookie_file:
                cookies = {}
                with open(cookie_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split('\t')
                            if len(parts) >= 7:
                                cookies[parts[5]] = parts[6]
                cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())

            if not cookie_str or 'sessionid' not in cookie_str:
                return jsonify({
                    'error': 'Instagram sessionid cookie required for private content',
                    'yt_dlp_error': error_msg
                }), 401

            # Use Instagram's private media info API
            # Convert shortcode to media_id (pk)
            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
            media_id = 0
            for char in shortcode:
                media_id = media_id * 64 + alphabet.index(char)

            proxy_url = config.get_proxy_url('instagram')
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}) if proxy_url else urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)

            api_url = f'https://i.instagram.com/api/v1/media/{media_id}/info/'
            req = urllib.request.Request(api_url, headers={
                'X-IG-App-ID': '936619743392459',
                'X-ASBD-ID': '198387',
                'X-IG-WWW-Claim': '0',
                'Origin': 'https://www.instagram.com',
                'Accept': '*/*',
                'Cookie': cookie_str,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            })

            response = opener.open(req, timeout=30)
            api_data = json_mod.loads(response.read().decode())

            items = api_data.get('items', [])
            if not items:
                return jsonify({
                    'error': 'No media items found via private API',
                    'yt_dlp_error': error_msg
                }), 404

            item = items[0]

            # Find the best video URL
            video_url = None
            video_versions = item.get('video_versions', [])
            if video_versions:
                # Sort by width (best quality first)
                video_versions.sort(key=lambda v: v.get('width', 0), reverse=True)
                video_url = video_versions[0].get('url')

            if not video_url:
                # Try carousel media
                carousel = item.get('carousel_media', [])
                for cm in carousel:
                    vv = cm.get('video_versions', [])
                    if vv:
                        vv.sort(key=lambda v: v.get('width', 0), reverse=True)
                        video_url = vv[0].get('url')
                        break

            if not video_url:
                return jsonify({
                    'error': 'No video found in media response (might be an image post)',
                    'yt_dlp_error': error_msg
                }), 404

            # Download the video directly
            platform_dir = config.DOWNLOAD_DIR / 'instagram'
            platform_dir.mkdir(exist_ok=True)

            title = sanitize_filename(
                item.get('caption', {}).get('text', '')[:50] if item.get('caption') else f'private_{shortcode}'
            ) or f'private_{shortcode}'
            filename = f"{title}-{shortcode}.mp4"
            output_path = platform_dir / filename

            video_req = urllib.request.Request(video_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            })
            video_response = opener.open(video_req, timeout=120)

            with open(output_path, 'wb') as f:
                while True:
                    chunk = video_response.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

            file_size = output_path.stat().st_size / (1024 * 1024)

            logger.info(f"Private Instagram download via API fallback: {filename} ({file_size:.2f} MB)")
            return jsonify({
                'success': True,
                'method': 'instagram-private-api',
                'platform': 'instagram',
                'title': title,
                'file_path': str(output_path),
                'file_name': filename,
                'file_size_mb': round(file_size, 2),
                'duration': item.get('video_duration'),
                'ext': 'mp4'
            })

        except Exception as fallback_error:
            logger.exception(f"Instagram private API fallback also failed: {fallback_error}")
            return jsonify({
                'error': 'Both yt-dlp and Instagram private API failed',
                'yt_dlp_error': error_msg,
                'api_error': str(fallback_error)
            }), 500


@app.route('/api/serve/<path:filepath>', methods=['GET'])
def serve_file(filepath):
    """Serve a downloaded file (optional - for HTTP access to files)."""
    full_path = config.DOWNLOAD_DIR / filepath

    if not full_path.exists():
        return jsonify({'error': 'File not found'}), 404

    # Security: ensure path is within DOWNLOAD_DIR
    try:
        full_path.resolve().relative_to(config.DOWNLOAD_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Access denied'}), 403

    return send_file(full_path)


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    logger.info(f"Starting YT-DLP Local Service v{config.VERSION}")
    logger.info(f"Download directory: {config.DOWNLOAD_DIR}")
    logger.info(f"Listening on {config.HOST}:{config.PORT}")

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=False,
        threaded=True
    )
