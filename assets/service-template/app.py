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


def rejection_for(url: str, platform: str):
    """Return a clear error for URLs the extractors do not support.

    vm.tiktok.com and vt.tiktok.com short links are left alone; they are
    video links and the TikTok extractor already resolves them.
    """
    if platform == 'tiktok' and re.search(r'/photo(?:/|$)', url, re.I):
        return (
            'TikTok /photo/ URLs are photo posts. The video extractor does not '
            'accept photo posts. Pass a /video/ URL. vm.tiktok.com and '
            'vt.tiktok.com short links to videos still work.'
        )
    if platform != 'instagram':
        return None

    path = urllib.parse.urlparse(url).path.strip('/')
    parts = [part for part in path.split('/') if part]
    if not parts:
        return None
    if parts[0].lower() == 'share':
        return (
            'Instagram /share/ URLs are excluded by the Instagram extractor '
            '(the /p|reel|tv matcher skips share/). Open the share link and '
            'pass the canonical /p/, /reel/, or /tv/ URL.'
        )
    reserved = {'p', 'reel', 'reels', 'tv', 'stories', 'explore', 'accounts', 'share'}
    if len(parts) == 1 and parts[0].lower() not in reserved:
        return (
            'instagram:user is broken in yt-dlp 2026.08.19 '
            '(InstagramUserIE sets _WORKING = False). Pass a /p/, /reel/, /tv/, '
            'or /stories/ URL (including highlights), not a profile URL.'
        )
    return None


def sanitize_filename(title: str) -> str:
    """Sanitize title for use as filename."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('._')
    if len(sanitized) > 80:
        sanitized = sanitized[:80]
    return sanitized or 'video'


def get_video_id(info: dict) -> str:
    """Extract video ID from info dict."""
    if not isinstance(info, dict):
        return 'unknown'
    return info.get('id') or info.get('display_id') or 'unknown'


def wants_noplaylist(data: dict) -> bool:
    """noplaylist is off unless the caller asks for a single slide or frame."""
    if not data:
        return False
    return bool(data.get('noplaylist') or data.get('single_slide') or data.get('single_frame'))


def instagram_app_id(opts: dict) -> str:
    ig = (opts.get('extractor_args') or {}).get('instagram') or {}
    if isinstance(ig, dict):
        vals = ig.get('app_id') or [INSTAGRAM_WEB_APP_ID]
        if isinstance(vals, (list, tuple)) and vals:
            return str(vals[0])
    return INSTAGRAM_WEB_APP_ID


def with_instagram_app_id(opts: dict, app_id: str) -> dict:
    copied = copy.deepcopy(opts)
    copied.setdefault('extractor_args', {})
    ig = dict(copied['extractor_args'].get('instagram') or {})
    ig['app_id'] = [app_id]
    copied['extractor_args']['instagram'] = ig
    return copied


def is_ig_wall(message: str) -> bool:
    low = (message or '').lower()
    return any(marker in low for marker in IG_WALL_MARKERS)


def annotate_error(platform: str, message: str) -> str:
    """Surface TikTok status 10204 as an IP block with a concrete next step."""
    if platform == 'tiktok' and message and '10204' in message:
        return (
            'TikTok status 10204: IP block. Rotate proxy or source address. '
            + message
        )
    return message


def _apply_cookies_and_proxy(opts: dict, platform: str) -> None:
    """Attach existing cookie files and sticky proxies. Do not log secrets."""
    cookiefile = ''
    if platform == 'youtube' and config.YOUTUBE_COOKIES:
        cookiefile = config.YOUTUBE_COOKIES
        logger.info("Using YouTube cookies from configured file")
    elif platform == 'instagram' and config.INSTAGRAM_COOKIES:
        # yt-dlp rewrites the cookie file and can strip sessionid. Keep a
        # master file and hand the downloader a copy. If yt-dlp reports that
        # the jar was invalidated (login wall / "cookies are no longer valid"),
        # re-export from the browser; do not keep using that copy.
        master_cookies = config.INSTAGRAM_COOKIES.replace('.txt', '_master.txt')
        if os.path.exists(master_cookies):
            tmp_cookie = os.path.join(os.path.dirname(master_cookies), 'instagram_tmp.txt')
            shutil.copy2(master_cookies, tmp_cookie)
            cookiefile = tmp_cookie
            logger.info("Using Instagram cookies from master copy")
        else:
            cookiefile = config.INSTAGRAM_COOKIES
            logger.info("Using Instagram cookies from configured file")
    elif platform == 'tiktok' and config.TIKTOK_COOKIES:
        cookiefile = config.TIKTOK_COOKIES
        logger.info("Using TikTok cookies from configured file")
    elif platform == 'twitter' and config.TWITTER_COOKIES:
        cookiefile = config.TWITTER_COOKIES
        logger.info("Using X/Twitter cookies from configured file")

    if cookiefile:
        opts['cookiefile'] = cookiefile
    elif config.COOKIES_FROM_BROWSER_SPEC:
        # Optional --cookies-from-browser. Netscape cookie files win when set.
        opts['cookiesfrombrowser'] = config.COOKIES_FROM_BROWSER_SPEC
        logger.info("Using cookies-from-browser because no cookie file is set for %s", platform)

    proxy_url = config.get_proxy_url(platform)
    if proxy_url:
        opts['proxy'] = proxy_url
        logger.info(
            "Using proxy for %s: %s:%s",
            platform,
            config.PROXY_HOST,
            config.PROXY_PORTS.get(platform, config.PROXY_PORTS['default']),
        )


def get_ydl_opts(platform: str, audio_only: bool = False, download: bool = False,
                 platform_dir: Path = None, quality: str = 'best',
                 noplaylist: bool = False) -> dict:
    """Build yt-dlp options based on platform and requirements.

    Impersonation is not forced. curl-cffi is installed so an extractor can
    impersonate on its own; a global impersonate target is intentionally unset.
    """
    opts = {
        'quiet': True,
        'no_warnings': False,
        'extract_flat': False,
        'retries': 10,
        'extractor_retries': 3,
        'fragment_retries': 10,
        'sleep_interval_requests': 0.75,
        'sleep_interval': 5,
        'max_sleep_interval': 10,
    }

    _apply_cookies_and_proxy(opts, platform)

    if platform == 'instagram':
        # Documented extractor arg. 'web' is the default app id
        # (936619743392459). Do not start on ios.
        opts['extractor_args'] = {'instagram': {'app_id': [INSTAGRAM_WEB_APP_ID]}}
        # UA must match the browser that exported the cookies. Override with
        # USER_AGENT when the cookie jar came from a different browser.
        opts['http_headers'] = {
            'User-Agent': config.USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Site': 'same-origin',
        }
    elif platform == 'twitter' and not opts.get('cookiefile') and not opts.get('cookiesfrombrowser'):
        # Logged-out X/Twitter only. Syndication is not used with logged-in cookies.
        opts['extractor_args'] = {'twitter': {'api': ['syndication']}}

    if noplaylist:
        opts['noplaylist'] = True

    if not download:
        opts['skip_download'] = True
        return opts

    if platform_dir is None:
        raise ValueError('platform_dir is required when download=True')
    platform_dir = Path(platform_dir)
    platform_dir.mkdir(parents=True, exist_ok=True)

    # Relative outtmpl: an absolute template would ignore paths.home.
    opts['paths'] = {'home': str(platform_dir)}
    opts['outtmpl'] = OUTTMPL
    opts['writesubtitles'] = True
    opts['subtitleslangs'] = ['en.*', '.*-orig']
    opts['writeinfojson'] = True
    opts['writedescription'] = True

    if audio_only:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }]
    else:
        if quality == 'best':
            if platform in ['instagram', 'tiktok', 'twitter', 'facebook']:
                opts['format'] = 'best'
            else:
                opts['format'] = 'bestvideo+bestaudio/best'
        elif quality == 'worst':
            opts['format'] = 'worst'
        elif str(quality).isdigit():
            height = str(quality)
            if platform in ['instagram', 'tiktok', 'twitter', 'facebook']:
                opts['format'] = f'best[height<={height}]/best'
            else:
                opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
        else:
            opts['format'] = 'best'

    if platform == 'youtube' and not audio_only:
        opts['merge_output_format'] = 'mp4'

    return opts


@retry_on_transient
def _ydl_once(url: str, opts: dict, download: bool):
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=download)


def run_ydl(url: str, opts: dict, download: bool, platform: str):
    """Run yt-dlp. Instagram web app_id retries once with app_id=ios on a login wall or empty media."""
    try:
        return _ydl_once(url, opts, download)
    except Exception as exc:
        if (
            platform == 'instagram'
            and instagram_app_id(opts) != INSTAGRAM_IOS_APP_ID
            and is_ig_wall(str(exc))
        ):
            logger.warning(
                "Instagram web app_id hit a login wall or empty media; retrying once with app_id=ios"
            )
            return _ydl_once(url, with_instagram_app_id(opts, INSTAGRAM_IOS_APP_ID), download)
        raise


def extract_info(url: str, noplaylist: bool = False):
    """Extract video information without downloading."""
    platform = detect_platform(url)
    reason = rejection_for(url, platform)
    if reason:
        raise ClientInputError(reason)
    opts = get_ydl_opts(platform, download=False, noplaylist=noplaylist)
    info = run_ydl(url, opts, download=False, platform=platform)
    return info, platform


def snapshot_files(directory: Path) -> dict:
    found = {}
    if directory and directory.exists():
        for path in directory.rglob('*'):
            if path.is_file():
                found[str(path)] = path.stat().st_mtime_ns
    return found


def files_written_since(directory: Path, before: dict) -> list:
    """Every finished file from this run, including playlist entries and sidecars.

    Does not assume a single title-id file. Carousels and stories write one
    media file per item plus .info.json, .description, and subtitles.
    """
    written = []
    if not directory or not directory.exists():
        return written
    for path in directory.rglob('*'):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith('.part') or name.endswith('.ytdl') or name.endswith('.temp'):
            continue
        previous = before.get(str(path))
        if previous is None or path.stat().st_mtime_ns > previous:
            written.append(path)
    written.sort(key=lambda item: (item.stat().st_mtime_ns, item.name))
    return written


def file_record(path: Path) -> dict:
    size = path.stat().st_size / (1024 * 1024)
    return {
        'file_path': str(path),
        'file_name': path.name,
        'file_size_mb': round(size, 2),
        'ext': path.suffix.lstrip('.'),
    }


def partition_outputs(paths: list):
    media = [path for path in paths if path.suffix.lower() in MEDIA_SUFFIXES]
    sidecars = [path for path in paths if path.suffix.lower() not in MEDIA_SUFFIXES]
    return media, sidecars


def download_result(info: dict, platform: str, written: list) -> dict:
    media, sidecars = partition_outputs(written)
    if not media and not sidecars:
        raise Exception("Download completed but file not found")
    primary = media[0] if media else sidecars[0]
    primary_meta = file_record(primary)
    title = None
    duration = None
    if isinstance(info, dict):
        title = info.get('title')
        duration = info.get('duration')
        if info.get('_type') == 'playlist' and not title:
            title = info.get('playlist_title')
    return {
        'success': True,
        'platform': platform,
        'title': title,
        'file_path': primary_meta['file_path'],
        'file_name': primary_meta['file_name'],
        'file_size_mb': primary_meta['file_size_mb'],
        'duration': duration,
        'ext': primary_meta['ext'],
        'file_count': len(media) or len(sidecars),
        'files': [file_record(path) for path in (media or sidecars)],
        'sidecars': [file_record(path) for path in sidecars],
    }


def perform_download(url: str, platform: str, quality: str, audio_only: bool, noplaylist: bool):
    platform_dir = config.DOWNLOAD_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_files(platform_dir)
    opts = get_ydl_opts(
        platform,
        audio_only=audio_only,
        download=True,
        platform_dir=platform_dir,
        quality=quality,
        noplaylist=noplaylist,
    )
    info = run_ydl(url, opts, download=True, platform=platform)
    written = files_written_since(platform_dir, before)
    return download_result(info, platform, written)


def _load_netscape_cookies(cookie_file: str) -> dict:
    """Read a Netscape cookie file. Values are never logged."""
    cookies = {}
    if not cookie_file or not os.path.exists(cookie_file):
        return cookies
    with open(cookie_file) as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            parts = stripped.split('\t')
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return cookies


def _ig_cookie_header() -> str:
    master_path = config.INSTAGRAM_COOKIES.replace('.txt', '_master.txt') if config.INSTAGRAM_COOKIES else ''
    cookie_file = master_path if master_path and os.path.exists(master_path) else config.INSTAGRAM_COOKIES
    cookies = _load_netscape_cookies(cookie_file)
    if not cookies:
        return ''
    return '; '.join(f'{key}={value}' for key, value in cookies.items())


def _best_video_url(media: dict):
    versions = [item for item in (media.get('video_versions') or []) if item.get('url')]
    if not versions:
        return None
    versions.sort(key=lambda item: item.get('width') or 0, reverse=True)
    return versions[0]['url']


def _walk_ig_media(media: dict, found: list) -> None:
    if not isinstance(media, dict):
        return
    video_url = _best_video_url(media)
    if video_url:
        media_id = str(media.get('pk') or media.get('id') or 'media')
        found.append((media_id, video_url, media))
    for child in media.get('carousel_media') or []:
        _walk_ig_media(child, found)


def _ig_media_dicts(payload: dict) -> list:
    if not isinstance(payload, dict):
        return []
    items = payload.get('items')
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    reels = payload.get('reels')
    if isinstance(reels, dict):
        collected = []
        for reel in reels.values():
            if isinstance(reel, dict):
                collected.extend(item for item in (reel.get('items') or []) if isinstance(item, dict))
        return collected
    return [payload]


def _ig_opener():
    proxy_url = config.get_proxy_url('instagram')
    if proxy_url:
        handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
    else:
        handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(handler)


def _ig_private_headers(cookie_header: str) -> dict:
    return {
        'X-IG-App-ID': IG_PRIVATE_APP_ID,
        'X-ASBD-ID': IG_ASBD_ID,
        'X-IG-WWW-Claim': '0',
        'Origin': 'https://www.instagram.com',
        'Accept': '*/*',
        'Cookie': cookie_header,
        # Same configurable UA as yt-dlp. Must match the cookie export browser.
        'User-Agent': config.USER_AGENT,
    }


def _shortcode_to_media_id(shortcode: str) -> int:
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return media_id


def instagram_private_download(url: str):
    """Direct Instagram private API fallback for posts, carousels, stories, and highlights.

    Accepts /p/, /reel/, /reels/, /tv/, and /stories/ (including highlights).
    /share/ is excluded and instagram:user profiles are rejected.
    """
    reason = rejection_for(url, 'instagram')
    if reason:
        return {'error': reason}, 400

    cookie_header = _ig_cookie_header()
    if not cookie_header or 'sessionid=' not in cookie_header:
        return {
            'error': 'Instagram sessionid cookie required for private content. Re-export a Netscape cookie file after a fresh login.',
        }, 401

    story = re.search(r'/stories/(?P<user>[^/?#]+)(?:/(?P<sid>\d+))?', url, re.I)
    shortcode_match = re.search(r'/(?:p|reels?|tv)/([A-Za-z0-9_-]+)', url)
    if story:
        user = story.group('user')
        sid = story.group('sid')
        if user.lower() == 'highlights':
            if not sid:
                return {'error': 'Highlight URL is missing a highlight id (/stories/highlights/<id>).'}, 400
            api_url = f'https://i.instagram.com/api/v1/feed/reels_media/?reel_ids=highlight:{sid}'
        elif sid:
            api_url = f'https://i.instagram.com/api/v1/media/{sid}/info/'
        else:
            return {
                'error': (
                    'User story tray URLs need a numeric story id (/stories/<user>/<id>) '
                    'or a highlight id (/stories/highlights/<id>).'
                ),
            }, 400
    elif shortcode_match:
        try:
            media_id = _shortcode_to_media_id(shortcode_match.group(1))
        except ValueError:
            return {'error': 'Cannot extract a media id from this Instagram URL'}, 400
        api_url = f'https://i.instagram.com/api/v1/media/{media_id}/info/'
    else:
        return {
            'error': (
                'Cannot extract a post shortcode or story id. Supported private-API '
                'URLs are /p/, /reel/, /reels/, /tv/, and /stories/ (including highlights).'
            ),
        }, 400

    opener = _ig_opener()
    req = urllib.request.Request(api_url, headers=_ig_private_headers(cookie_header))
    response = opener.open(req, timeout=30)
    payload = json.loads(response.read().decode())

    found = []
    for media in _ig_media_dicts(payload):
        _walk_ig_media(media, found)
    if not found:
        return {
            'error': 'No video found in media response (might be an image post or an empty story)',
        }, 404

    platform_dir = config.DOWNLOAD_DIR / 'instagram'
    platform_dir.mkdir(parents=True, exist_ok=True)
    written = []
    multiple = len(found) > 1
    for index, (media_id, video_url, media) in enumerate(found, start=1):
        caption = ''
        caption_obj = media.get('caption')
        if isinstance(caption_obj, dict):
            caption = (caption_obj.get('text') or '')[:80]
        title = sanitize_filename(caption or f'instagram_{media_id}')
        index_part = f' {index}' if multiple else ''
        filename = f'{title} [{media_id}]{index_part}.mp4'
        output_path = platform_dir / filename
        video_req = urllib.request.Request(video_url, headers={'User-Agent': config.USER_AGENT})
        video_response = opener.open(video_req, timeout=120)
        with open(output_path, 'wb') as handle:
            while True:
                chunk = video_response.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
        written.append(output_path)

    info = {
        'title': written[0].name if written else None,
        '_type': 'playlist' if multiple else 'video',
        'duration': found[0][2].get('video_duration') if found else None,
    }
    result = download_result(info, 'instagram', written)
    result['method'] = 'instagram-private-api'
    result['title'] = sanitize_filename(
        ((found[0][2].get('caption') or {}) if isinstance(found[0][2].get('caption'), dict) else {}).get('text', '')[:80]
        if found else ''
    ) or result['file_name']
    logger.info("Instagram private API fallback wrote %s file(s)", len(written))
    return result, 200


# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        'service': 'yt-dlp-local',
        'version': config.VERSION,
        'endpoints': [
            '/health', '/api/extract', '/api/download', '/api/audio',
            '/api/formats', '/api/instagram/private',
        ]
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint. Cookie values and proxy passwords are not returned."""
    return jsonify({
        'status': 'ok',
        'version': config.VERSION,
        'download_dir': str(config.DOWNLOAD_DIR),
        'cookies': {
            'youtube': bool(config.YOUTUBE_COOKIES),
            'instagram': bool(config.INSTAGRAM_COOKIES),
            'tiktok': bool(config.TIKTOK_COOKIES),
            'twitter': bool(config.TWITTER_COOKIES),
        },
        'cookies_from_browser': bool(config.COOKIES_FROM_BROWSER_SPEC),
        'proxy': {
            'enabled': bool(config.PROXY_HOST),
            'host': config.PROXY_HOST or None,
            'ports': config.PROXY_PORTS if config.PROXY_HOST else None,
        }
    })


def _client_error(exc: ClientInputError):
    return jsonify({'error': 'Unsupported URL', 'message': str(exc)}), 400


@app.route('/api/extract', methods=['POST'])
def api_extract():
    """Extract video metadata without downloading."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Extracting metadata: {url}")

    try:
        info, platform = extract_info(url, noplaylist=wants_noplaylist(data))
        if not isinstance(info, dict):
            info = {}

        formats = info.get('formats') or []
        resolutions = set()
        for fmt in formats:
            if fmt and fmt.get('height'):
                resolutions.add(f"{fmt['height']}p")
        if any(fmt.get('acodec') and fmt.get('acodec') != 'none' for fmt in formats if fmt):
            resolutions.add('audio-only')

        response = {
            'success': True,
            'platform': platform,
            'id': get_video_id(info),
            'title': info.get('title') or info.get('playlist_title'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader') or info.get('channel'),
            'upload_date': info.get('upload_date'),
            'view_count': info.get('view_count'),
            'description': info.get('description', '')[:500] if info.get('description') else None,
            'formats_available': sorted(list(resolutions), key=lambda item: (item != 'audio-only', item), reverse=True),
        }
        if info.get('_type') == 'playlist':
            entries = [entry for entry in (info.get('entries') or []) if isinstance(entry, dict)]
            response['playlist_count'] = info.get('playlist_count') or len(entries)
            response['entry_ids'] = [get_video_id(entry) for entry in entries]

        logger.info(f"Extracted: {response.get('title')} ({platform})")
        return jsonify(response)

    except ClientInputError as exc:
        return _client_error(exc)
    except yt_dlp.utils.DownloadError as exc:
        error_msg = annotate_error(detect_platform(url), str(exc))
        logger.error(f"Extraction failed: {error_msg}")
        return jsonify({'error': 'Download error', 'message': error_msg}), 400
    except Exception as exc:
        logger.exception("Extraction failed")
        return jsonify({
            'error': 'Extraction failed',
            'message': annotate_error(detect_platform(url), str(exc)),
        }), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    """Download video to local storage."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    quality = data.get('quality', 'best')
    audio_only = data.get('audio_only', False)
    noplaylist = wants_noplaylist(data)
    platform = detect_platform(url)

    logger.info(f"Downloading: {url} (quality={quality}, audio_only={audio_only}, noplaylist={noplaylist})")

    try:
        reason = rejection_for(url, platform)
        if reason:
            raise ClientInputError(reason)
        return jsonify(perform_download(url, platform, quality, audio_only, noplaylist))
    except ClientInputError as exc:
        return _client_error(exc)
    except Exception as exc:
        error_msg = annotate_error(platform, str(exc))
        logger.error(f"Download failed: {error_msg}")

        if platform == 'instagram' and any(keyword in error_msg.lower() for keyword in IG_PRIVATE_FALLBACK_MARKERS):
            logger.info("Attempting Instagram private API fallback...")
            try:
                payload, status = instagram_private_download(url)
                if status == 200:
                    return jsonify(payload), 200
                payload = dict(payload)
                payload['yt_dlp_error'] = error_msg
                return jsonify(payload), status
            except Exception as fallback_err:
                logger.error("Instagram fallback also failed: %s", type(fallback_err).__name__)
                return jsonify({
                    'error': 'Both yt-dlp and Instagram private API failed',
                    'yt_dlp_error': error_msg,
                    'api_error': str(fallback_err),
                }), 500

        return jsonify({'error': 'Download error', 'message': error_msg}), 400


@app.route('/api/audio', methods=['POST'])
def api_audio():
    """Extract audio only - convenience endpoint."""
    data = request.json or {}
    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    platform = detect_platform(url)
    logger.info(f"Extracting audio: {url}")

    try:
        reason = rejection_for(url, platform)
        if reason:
            raise ClientInputError(reason)
        return jsonify(perform_download(
            url,
            platform,
            quality='best',
            audio_only=True,
            noplaylist=wants_noplaylist(data),
        ))
    except ClientInputError as exc:
        return _client_error(exc)
    except Exception as exc:
        logger.exception("Audio extraction failed")
        return jsonify({
            'error': 'Audio extraction failed',
            'message': annotate_error(platform, str(exc)),
        }), 500


@app.route('/api/formats', methods=['POST'])
def api_formats():
    """List available formats for a URL."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info(f"Listing formats: {url}")

    try:
        info, platform = extract_info(url, noplaylist=wants_noplaylist(data))
        formats = []
        for fmt in (info.get('formats') or []) if isinstance(info, dict) else []:
            if not fmt:
                continue
            formats.append({
                'format_id': fmt.get('format_id'),
                'ext': fmt.get('ext'),
                'resolution': f"{fmt.get('height', '?')}p" if fmt.get('height') else 'audio',
                'width': fmt.get('width'),
                'height': fmt.get('height'),
                'fps': fmt.get('fps'),
                'vcodec': fmt.get('vcodec'),
                'acodec': fmt.get('acodec'),
                'filesize_mb': round(fmt.get('filesize', 0) / (1024 * 1024), 2) if fmt.get('filesize') else None,
                'tbr': fmt.get('tbr'),
            })

        return jsonify({
            'success': True,
            'platform': platform,
            'title': info.get('title') if isinstance(info, dict) else None,
            'formats': formats,
        })
    except ClientInputError as exc:
        return _client_error(exc)
    except Exception as exc:
        logger.exception("Format listing failed")
        return jsonify({
            'error': 'Failed to list formats',
            'message': annotate_error(detect_platform(url), str(exc)),
        }), 500


@app.route('/api/instagram/private', methods=['POST'])
def api_instagram_private():
    """Download Instagram content that requires authentication (private accounts, stories).

    Tries yt-dlp first (web app id, then one ios retry on login wall / empty media).
    Falls back to the private API for /p/, /reel/, /reels/, /tv/, and /stories/
    including highlights.
    """
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    logger.info("Instagram private download requested")

    try:
        if detect_platform(url) != 'instagram':
            return jsonify({'error': 'Not an Instagram URL'}), 400
        reason = rejection_for(url, 'instagram')
        if reason:
            raise ClientInputError(reason)
        result = perform_download(
            url,
            'instagram',
            quality=data.get('quality', 'best'),
            audio_only=False,
            noplaylist=wants_noplaylist(data),
        )
        result['method'] = 'yt-dlp-authenticated'
        return jsonify(result)
    except ClientInputError as exc:
        return _client_error(exc)
    except Exception as exc:
        error_msg = annotate_error('instagram', str(exc))
        logger.warning("Standard yt-dlp failed for private content")
        try:
            payload, status = instagram_private_download(url)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload['yt_dlp_error'] = error_msg
            return jsonify(payload), status
        except Exception as fallback_error:
            logger.exception("Instagram private API fallback also failed")
            return jsonify({
                'error': 'Both yt-dlp and Instagram private API failed',
                'yt_dlp_error': error_msg,
                'api_error': str(fallback_error),
            }), 500


@app.route('/api/serve/<path:filepath>', methods=['GET'])
def serve_file(filepath):
    """Serve a downloaded file (optional - for HTTP access to files)."""
    full_path = config.DOWNLOAD_DIR / filepath

    if not full_path.exists():
        return jsonify({'error': 'File not found'}), 404

    try:
        full_path.resolve().relative_to(config.DOWNLOAD_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Access denied'}), 403

    return send_file(full_path)


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
