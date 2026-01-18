"""
Spotify Service for LeLamp

Provides Spotify playback control via Spotify Connect.
Requires:
- Spotify Premium account
- Raspotify installed (makes Pi a Spotify Connect device)
- Spotify API credentials (client_id, client_secret)

OAuth Flow:
1. First run: Opens browser for authentication
2. After auth: Saves refresh_token to .env
3. Subsequent runs: Uses refresh_token automatically
"""

import os
import logging
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass
from pathlib import Path

from lelamp.user_data import USER_DATA_DIR, ensure_user_data_dir

# Spotify cache path in user data directory
SPOTIFY_CACHE_PATH = USER_DATA_DIR / ".spotify_cache"

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Quiet noisy HTTP loggers from spotipy/requests/urllib3
logging.getLogger("spotipy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class SpotifyConfig:
    """Spotify service configuration."""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    # Note: Spotify requires 127.0.0.1, not localhost
    redirect_uri: str = "http://127.0.0.1:8888/callback"
    device_name: str = "lelamp"  # Name of the Spotify Connect device
    scope: str = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private user-library-read"


class SpotifyService:
    """
    Spotify playback control service.

    Uses Spotify Web API to control playback on a Spotify Connect device
    (typically raspotify running on the same Pi).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Spotify service.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._sp: Optional[spotipy.Spotify] = None
        self._device_id: Optional[str] = None
        self._current_track: Optional[Dict] = None
        self._current_audio_features: Optional[Dict] = None
        self._is_playing: bool = False
        self._poll_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_track_change: Optional[Callable[[Dict], None]] = None
        self.on_playback_state_change: Optional[Callable[[bool], None]] = None

        # Parse config
        config = config or {}
        self.config = SpotifyConfig(
            enabled=config.get("enabled", False),
            client_id=config.get("client_id", os.getenv("SPOTIFY_CLIENT_ID", "")),
            client_secret=config.get("client_secret", os.getenv("SPOTIFY_CLIENT_SECRET", "")),
            redirect_uri=config.get("redirect_uri", os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")),
            device_name=config.get("device_name", "raspotify"),
            scope=config.get("scope", SpotifyConfig.scope),
        )

        if not SPOTIPY_AVAILABLE:
            self.logger.warning("spotipy not installed. Run: uv add spotipy")
            self.config.enabled = False

    def _get_auth_manager(self) -> SpotifyOAuth:
        """Create Spotify OAuth manager."""
        # Ensure user data directory exists for cache
        ensure_user_data_dir()
        return SpotifyOAuth(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            redirect_uri=self.config.redirect_uri,
            scope=self.config.scope,
            cache_path=str(SPOTIFY_CACHE_PATH),
            open_browser=False,
        )

    def authenticate(self, interactive: bool = True) -> bool:
        """
        Authenticate with Spotify.

        Args:
            interactive: If True, opens browser for OAuth flow if needed

        Returns:
            True if authenticated successfully
        """
        if not self.config.client_id or not self.config.client_secret:
            self.logger.info("Spotify credentials not configured - service disabled")
            return False

        try:
            auth_manager = self._get_auth_manager()

            # Check if we have a cached token
            token_info = auth_manager.get_cached_token()

            if not token_info:
                if not interactive:
                    self.logger.warning("Spotify not authenticated - run setup to enable")
                    return False

                # Need to do OAuth flow
                auth_url = auth_manager.get_authorize_url()
                print(f"\nOpen this URL in your browser to authorize:")
                print(f"\n  {auth_url}\n")
                print(f"Waiting for authorization...")

                # Start callback server
                auth_code = self._wait_for_callback(auth_url)
                if not auth_code:
                    self.logger.error("Failed to get authorization code")
                    return False

                # Exchange code for token
                token_info = auth_manager.get_access_token(auth_code)

            # Create Spotify client
            self._sp = spotipy.Spotify(auth_manager=auth_manager)

            # Test the connection
            user = self._sp.current_user()
            self.logger.info(f"Authenticated as: {user['display_name']}")

            return True

        except Exception as e:
            self.logger.error(f"Spotify authentication failed: {e}")
            return False

    def _wait_for_callback(self, auth_url: str, timeout: int = 120) -> Optional[str]:
        """
        Wait for OAuth callback with authorization code.

        Args:
            auth_url: Spotify authorization URL
            timeout: Timeout in seconds

        Returns:
            Authorization code or None
        """
        auth_code = None
        server_ready = threading.Event()

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal auth_code
                parsed = urlparse(self.path)
                if parsed.path == "/callback":
                    params = parse_qs(parsed.query)
                    if "code" in params:
                        auth_code = params["code"][0]
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(b"""
                            <html><body>
                            <h1>Spotify Authentication Successful!</h1>
                            <p>You can close this window and return to LeLamp.</p>
                            </body></html>
                        """)
                    else:
                        self.send_response(400)
                        self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress server logs

        # Parse redirect URI for port
        parsed = urlparse(self.config.redirect_uri)
        port = parsed.port or 8888

        def run_server():
            nonlocal auth_code
            try:
                server = HTTPServer(("", port), CallbackHandler)
                server.timeout = 1
                server_ready.set()
                start_time = time.time()
                while auth_code is None and (time.time() - start_time) < timeout:
                    server.handle_request()
                server.server_close()
            except Exception as e:
                logger.error(f"Callback server error: {e}")

        # Start server in background
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to be ready
        server_ready.wait(timeout=5)

        # Don't try to open browser - we're likely on a headless device
        # URL was already printed by authenticate()

        # Wait for auth
        server_thread.join(timeout=timeout)
        return auth_code

    def start(self) -> bool:
        """
        Start the Spotify service.

        Returns:
            True if started successfully
        """
        if not self.config.enabled:
            self.logger.info("Spotify service disabled")
            return False

        if self._running:
            return True

        # Authenticate
        if not self.authenticate(interactive=False):
            self.logger.warning("Spotify not authenticated. Run setup first.")
            return False

        # Find device
        self._find_device()

        # Start polling thread
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_playback, daemon=True)
        self._poll_thread.start()

        self.logger.info("Spotify service started")
        return True

    def stop(self):
        """Stop the Spotify service."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2)
        self.logger.info("Spotify service stopped")

    def _find_device(self) -> Optional[str]:
        """Find the Spotify Connect device."""
        if not self._sp:
            return None

        try:
            devices = self._sp.devices()
            device_list = devices.get("devices", [])

            # Priority 1: Look for configured device name
            for device in device_list:
                if self.config.device_name.lower() in device["name"].lower():
                    self._device_id = device["id"]
                    self.logger.info(f"Found Spotify device: {device['name']} ({device['id']})")
                    return self._device_id

            # Priority 2: Use any active device
            for device in device_list:
                if device.get("is_active"):
                    self._device_id = device["id"]
                    self.logger.info(f"Using active device: {device['name']}")
                    return self._device_id

            # Priority 3: Use ANY available device (last resort)
            if device_list:
                device = device_list[0]
                self._device_id = device["id"]
                self.logger.warning(f"No active device, using first available: {device['name']}")
                return self._device_id

            self.logger.warning(f"Device '{self.config.device_name}' not found. Available: {[d['name'] for d in device_list]}")
            return None

        except Exception as e:
            self.logger.error(f"Error finding device: {e}")
            return None

    def _poll_playback(self):
        """Poll playback state for changes."""
        print("\033[95m🎵 SPOTIFY: Playback polling started\033[0m")
        while self._running:
            try:
                playback = self._sp.current_playback()

                # Track playback state changes (playing/paused)
                is_now_playing = playback.get("is_playing", False) if playback else False
                if is_now_playing != self._is_playing:
                    self._is_playing = is_now_playing
                    print(f"\033[95m🎵 SPOTIFY: Playback state changed → {'PLAYING' if is_now_playing else 'STOPPED'}\033[0m")
                    if self.on_playback_state_change:
                        self.on_playback_state_change(is_now_playing)
                    else:
                        print("\033[95m🎵 SPOTIFY: WARNING - no on_playback_state_change callback set!\033[0m")

                if playback and playback.get("item"):
                    track = playback["item"]
                    track_id = track.get("id")

                    # Check for track change
                    if self._current_track is None or self._current_track.get("id") != track_id:
                        self._current_track = track
                        # Fetch audio features (includes BPM) for new track
                        self._fetch_audio_features(track_id)
                        if self.on_track_change:
                            self.on_track_change(self._get_track_info(track))

                time.sleep(2)  # Poll every 2 seconds
            except Exception as e:
                self.logger.debug(f"Playback poll error: {e}")
                time.sleep(5)

    def _fetch_audio_features(self, track_id: str):
        """Fetch audio features for a track (includes tempo/BPM)."""
        if not self._sp or not track_id:
            self._current_audio_features = None
            return

        try:
            features = self._sp.audio_features([track_id])
            if features and features[0]:
                self._current_audio_features = features[0]
                bpm = features[0].get('tempo', 0)
                energy = features[0].get('energy', 0)
                danceability = features[0].get('danceability', 0)
                print(f"\033[95m🎵 SPOTIFY: Track BPM={bpm:.1f}, energy={energy:.2f}, danceability={danceability:.2f}\033[0m")
            else:
                self._current_audio_features = None
        except Exception as e:
            self.logger.debug(f"Error fetching audio features: {e}")
            self._current_audio_features = None

    def _get_track_info(self, track: Dict) -> Dict:
        """Extract useful track info."""
        if not track:
            return {}
        artists = track.get("artists", []) or []
        return {
            "id": track.get("id"),
            "name": track.get("name"),
            "artist": ", ".join(a.get("name", "") for a in artists if a),
            "album": (track.get("album") or {}).get("name"),
            "duration_ms": track.get("duration_ms"),
            "uri": track.get("uri"),
        }

    # ==================== Playback Control ====================

    def play(self, uri: Optional[str] = None, context_uri: Optional[str] = None) -> bool:
        """
        Start or resume playback.

        Args:
            uri: Spotify URI of track to play (e.g., "spotify:track:xxx")
            context_uri: Spotify URI of album/playlist (e.g., "spotify:playlist:xxx")

        Returns:
            True if successful
        """
        if not self._sp:
            return False

        try:
            # Always refresh device list to get current state
            self._find_device()

            if not self._device_id:
                self.logger.error("No Spotify device available")
                return False

            # Check if the configured device is active
            devices = self._sp.devices()
            device_list = devices.get("devices", [])
            target_device = None
            active_device = None

            for device in device_list:
                if device["id"] == self._device_id:
                    target_device = device
                if device.get("is_active"):
                    active_device = device

            # If our target device exists but isn't active, transfer playback first
            # Use force_play=True to wake up inactive/sleeping devices
            if target_device and (not active_device or active_device["id"] != self._device_id):
                self.logger.info(f"Transferring playback to {target_device['name']} (force_play=True)")
                self._sp.transfer_playback(self._device_id, force_play=True)
                time.sleep(1.5)  # Give raspotify more time to wake up

                # Re-check that device is now active
                devices = self._sp.devices()
                for device in devices.get("devices", []):
                    if device["id"] == self._device_id and device.get("is_active"):
                        self.logger.info(f"Device {device['name']} is now active")
                        break

            kwargs = {"device_id": self._device_id}
            if uri:
                kwargs["uris"] = [uri]
            if context_uri:
                kwargs["context_uri"] = context_uri

            self._sp.start_playback(**kwargs)
            self.logger.info(f"Started playback on device {self._device_id}")

            # Verify playback actually started
            time.sleep(0.5)
            playback = self._sp.current_playback()
            if playback and playback.get("is_playing"):
                self.logger.info("Playback verified - music is playing")
                return True
            else:
                # Playback didn't start, try again
                self.logger.warning("Playback command succeeded but music not playing, retrying...")
                time.sleep(0.5)
                self._sp.start_playback(**kwargs)
                time.sleep(0.5)
                playback = self._sp.current_playback()
                if playback and playback.get("is_playing"):
                    self.logger.info("Retry successful - music is now playing")
                    return True
                self.logger.warning("Music still not playing after retry")
                return False

        except Exception as e:
            self.logger.error(f"Error starting playback: {e}")
            # Retry once with device refresh
            try:
                self.logger.info("Retrying playback after device refresh...")
                time.sleep(0.5)
                self._find_device()
                if self._device_id:
                    self._sp.transfer_playback(self._device_id, force_play=True)
                    time.sleep(1.5)
                    kwargs = {"device_id": self._device_id}
                    if uri:
                        kwargs["uris"] = [uri]
                    if context_uri:
                        kwargs["context_uri"] = context_uri
                    self._sp.start_playback(**kwargs)
                    time.sleep(0.5)
                    # Verify playback
                    playback = self._sp.current_playback()
                    if playback and playback.get("is_playing"):
                        self.logger.info("Retry successful!")
                        return True
            except Exception as retry_e:
                self.logger.error(f"Retry also failed: {retry_e}")
            return False

    def pause(self) -> bool:
        """Pause playback."""
        if not self._sp:
            return False
        try:
            self._sp.pause_playback(device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error pausing: {e}")
            return False

    def resume(self) -> bool:
        """Resume playback."""
        return self.play()

    def next_track(self) -> bool:
        """Skip to next track."""
        if not self._sp:
            return False
        try:
            self._sp.next_track(device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error skipping: {e}")
            return False

    def previous_track(self) -> bool:
        """Go to previous track."""
        if not self._sp:
            return False
        try:
            self._sp.previous_track(device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error going back: {e}")
            return False

    def set_volume(self, volume_percent: int) -> bool:
        """
        Set playback volume.

        Args:
            volume_percent: Volume level 0-100
        """
        if not self._sp:
            return False
        try:
            volume_percent = max(0, min(100, volume_percent))
            self._sp.volume(volume_percent, device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error setting volume: {e}")
            return False

    def seek(self, position_ms: int) -> bool:
        """
        Seek to position in current track.

        Args:
            position_ms: Position in milliseconds
        """
        if not self._sp:
            return False
        try:
            self._sp.seek_track(position_ms, device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error seeking: {e}")
            return False

    def shuffle(self, state: bool) -> bool:
        """Set shuffle mode."""
        if not self._sp:
            return False
        try:
            self._sp.shuffle(state, device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error setting shuffle: {e}")
            return False

    def repeat(self, state: str = "off") -> bool:
        """
        Set repeat mode.

        Args:
            state: "track", "context", or "off"
        """
        if not self._sp:
            return False
        try:
            self._sp.repeat(state, device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error setting repeat: {e}")
            return False

    # ==================== Playback Info ====================

    def get_current_track(self) -> Optional[Dict]:
        """Get currently playing track info."""
        if not self._sp:
            return None
        try:
            playback = self._sp.current_playback()
            if playback and playback.get("item"):
                return self._get_track_info(playback["item"])
            return None
        except Exception as e:
            self.logger.error(f"Error getting current track: {e}")
            return None

    def get_playback_state(self) -> Optional[Dict]:
        """Get full playback state."""
        if not self._sp:
            return None
        try:
            playback = self._sp.current_playback()
            if playback:
                return {
                    "is_playing": playback.get("is_playing", False),
                    "shuffle": playback.get("shuffle_state", False),
                    "repeat": playback.get("repeat_state", "off"),
                    "volume": playback.get("device", {}).get("volume_percent"),
                    "progress_ms": playback.get("progress_ms"),
                    "track": self._get_track_info(playback["item"]) if playback.get("item") else None,
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting playback state: {e}")
            return None

    def is_playing(self) -> bool:
        """Check if currently playing."""
        state = self.get_playback_state()
        return state.get("is_playing", False) if state else False

    def get_current_bpm(self) -> float:
        """
        Get the BPM (tempo) of the currently playing track.

        Returns:
            BPM as float, or 0.0 if not available
        """
        if self._current_audio_features:
            return self._current_audio_features.get("tempo", 0.0)
        return 0.0

    def get_energy(self) -> float:
        """
        Get energy level of current track (0.0-1.0).

        Energy represents intensity and activity. High energy tracks
        feel fast, loud, and noisy. Low energy tracks are calm/quiet.

        Returns:
            Energy as float 0.0-1.0, or 0.5 if not available
        """
        if not self._is_playing:
            return 0.0
        if self._current_audio_features:
            return self._current_audio_features.get("energy", 0.5)
        return 0.5  # Default to medium when playing but no features

    def get_audio_features(self) -> Optional[Dict]:
        """
        Get full audio features for the current track.

        Returns dict with keys like:
        - tempo: BPM
        - energy: 0-1 intensity
        - danceability: 0-1 how danceable
        - valence: 0-1 positivity/happiness
        - loudness: dB
        - key: 0-11 pitch class
        - mode: 0=minor, 1=major
        - time_signature: beats per bar
        """
        return self._current_audio_features

    # ==================== Search & Browse ====================

    def search(self, query: str, types: str = "track", limit: int = 10) -> List[Dict]:
        """
        Search Spotify.

        Args:
            query: Search query
            types: Comma-separated types: track, album, artist, playlist
            limit: Max results per type

        Returns:
            List of search results
        """
        if not self._sp:
            return []
        try:
            results = self._sp.search(q=query, type=types, limit=limit)
            if not results:
                self.logger.warning(f"Search returned no results for: {query}")
                return []
            items = []

            # Extract tracks
            if "tracks" in results and results["tracks"] and results["tracks"].get("items"):
                for track in results["tracks"]["items"]:
                    if track:  # Skip None items
                        items.append({
                            "type": "track",
                            **self._get_track_info(track)
                        })

            # Extract albums
            if "albums" in results and results["albums"] and results["albums"].get("items"):
                for album in results["albums"]["items"]:
                    if album:  # Skip None items
                        items.append({
                            "type": "album",
                            "id": album.get("id"),
                            "name": album.get("name"),
                            "artist": ", ".join(a["name"] for a in album.get("artists", [])),
                            "uri": album.get("uri"),
                        })

            # Extract artists
            if "artists" in results and results["artists"] and results["artists"].get("items"):
                for artist in results["artists"]["items"]:
                    if artist:  # Skip None items
                        items.append({
                            "type": "artist",
                            "id": artist.get("id"),
                            "name": artist.get("name"),
                            "uri": artist.get("uri"),
                        })

            # Extract playlists
            if "playlists" in results and results["playlists"] and results["playlists"].get("items"):
                for playlist in results["playlists"]["items"]:
                    if playlist:  # Skip None items
                        items.append({
                            "type": "playlist",
                            "id": playlist.get("id"),
                            "name": playlist.get("name"),
                            "owner": playlist.get("owner", {}).get("display_name"),
                            "uri": playlist.get("uri"),
                        })

            return items

        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return []

    def get_user_playlists(self, limit: int = 20) -> List[Dict]:
        """Get user's playlists."""
        if not self._sp:
            return []
        try:
            results = self._sp.current_user_playlists(limit=limit)
            return [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "uri": p["uri"],
                    "tracks": p.get("tracks", {}).get("total", 0),
                }
                for p in results.get("items", [])
            ]
        except Exception as e:
            self.logger.error(f"Error getting playlists: {e}")
            return []

    def get_liked_songs_uri(self) -> str:
        """Get URI for user's liked songs."""
        return "spotify:collection:tracks"

    def get_devices(self) -> List[Dict]:
        """Get available Spotify Connect devices."""
        if not self._sp:
            return []
        try:
            devices = self._sp.devices()
            return [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "type": d["type"],
                    "is_active": d.get("is_active", False),
                    "volume": d.get("volume_percent"),
                }
                for d in devices.get("devices", [])
            ]
        except Exception as e:
            self.logger.error(f"Error getting devices: {e}")
            return []

    def transfer_playback(self, device_id: str, play: bool = True) -> bool:
        """
        Transfer playback to a different device.

        Args:
            device_id: Target device ID
            play: Start playing on new device
        """
        if not self._sp:
            return False
        try:
            self._sp.transfer_playback(device_id, force_play=play)
            self._device_id = device_id
            return True
        except Exception as e:
            self.logger.error(f"Error transferring playback: {e}")
            return False

    # ==================== Queue ====================

    def add_to_queue(self, uri: str) -> bool:
        """
        Add track to queue.

        Args:
            uri: Spotify URI of track
        """
        if not self._sp:
            return False
        try:
            self._sp.add_to_queue(uri, device_id=self._device_id)
            return True
        except Exception as e:
            self.logger.error(f"Error adding to queue: {e}")
            return False

    # ==================== Convenience Methods ====================

    def play_search(self, query: str) -> bool:
        """
        Search and play the first result.

        Args:
            query: Search query (e.g., "bohemian rhapsody", "jazz playlist")
        """
        results = self.search(query, types="track,playlist,album", limit=1)
        if not results:
            self.logger.warning(f"No results for: {query}")
            return False

        result = results[0]
        if result["type"] == "track":
            return self.play(uri=result["uri"])
        else:
            return self.play(context_uri=result["uri"])

    def play_playlist(self, name: str) -> bool:
        """Play a playlist by name (searches user's playlists first)."""
        # Check user's playlists first
        playlists = self.get_user_playlists(limit=50)
        for p in playlists:
            if name.lower() in p["name"].lower():
                return self.play(context_uri=p["uri"])

        # Fall back to search
        return self.play_search(f"playlist {name}")

    def play_artist(self, name: str) -> bool:
        """Play an artist's top tracks."""
        results = self.search(name, types="artist", limit=1)
        if results:
            return self.play(context_uri=results[0]["uri"])
        return False

    def play_album(self, name: str, artist: Optional[str] = None) -> bool:
        """Play an album."""
        query = f"album:{name}"
        if artist:
            query += f" artist:{artist}"
        results = self.search(query, types="album", limit=1)
        if results:
            return self.play(context_uri=results[0]["uri"])
        return False

    def play_liked_songs(self) -> bool:
        """Play user's liked songs."""
        return self.play(context_uri=self.get_liked_songs_uri())
