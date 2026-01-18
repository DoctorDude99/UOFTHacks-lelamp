"""
Spotify API endpoints.

All /api/v1/spotify/* routes for Spotify OAuth and playback control.
"""

import os
import logging
import socket
import subprocess
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from api.deps import get_spotify_service, load_config, save_config, get_config
from lelamp.user_data import get_env_path, USER_ENV_FILE
import lelamp.globals as g

router = APIRouter()
logger = logging.getLogger(__name__)


def _load_env():
    """Load .env from user directory if it exists, otherwise fallback."""
    env_path = get_env_path()
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)


def get_local_ip():
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.get("/callback-url")
async def get_callback_url():
    """Get the callback URL with the current IP address."""
    ip = get_local_ip()
    callback_url = f"https://{ip}:8888/api/v1/spotify/auth/callback"
    return {
        "success": True,
        "ip": ip,
        "callback_url": callback_url
    }


@router.post("/credentials")
async def save_spotify_credentials(request: Request):
    """Save Spotify credentials to .env file."""
    data = await request.json()
    client_id = data.get("client_id", "").strip()
    client_secret = data.get("client_secret", "").strip()

    if not client_id or not client_secret:
        return {"success": False, "error": "Both Client ID and Client Secret are required"}

    try:
        env_path = USER_ENV_FILE

        # Read existing .env or create new
        env_lines = []
        if env_path.exists():
            with open(env_path, 'r') as f:
                env_lines = f.readlines()

        # Update or add Spotify credentials
        keys_to_update = {
            "SPOTIFY_CLIENT_ID": client_id,
            "SPOTIFY_CLIENT_SECRET": client_secret,
        }

        updated_keys = set()
        for i, line in enumerate(env_lines):
            for key, value in keys_to_update.items():
                if line.startswith(f"{key}="):
                    env_lines[i] = f"{key}={value}\n"
                    updated_keys.add(key)
                    break

        # Add missing keys
        for key, value in keys_to_update.items():
            if key not in updated_keys:
                env_lines.append(f"{key}={value}\n")

        # Write back to .env
        with open(env_path, 'w') as f:
            f.writelines(env_lines)

        # Reload environment variables
        _load_env()

        logger.info("Spotify credentials saved to .env")
        return {"success": True, "message": "Credentials saved successfully"}

    except Exception as e:
        logger.error(f"Failed to save Spotify credentials: {e}")
        return {"success": False, "error": str(e)}


@router.get("/status")
async def spotify_status():
    """Get Spotify connection and playback status."""
    _load_env()

    config = get_config()
    spotify_config = config.get("spotify", {})
    enabled = spotify_config.get("enabled", False)

    if not enabled:
        return {"enabled": False, "authenticated": False, "message": "Spotify disabled in config"}

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        return {
            "enabled": enabled,
            "authenticated": False,
            "message": "Spotify credentials not configured in .env file"
        }

    try:
        svc = get_spotify_service()
        if svc is None:
            return {
                "enabled": enabled,
                "authenticated": False,
                "message": "Spotify service not available"
            }

        # Update service config with latest env vars
        svc.config.client_id = client_id
        svc.config.client_secret = client_secret

        # Check if authenticated
        auth_manager = svc._get_auth_manager()
        token_info = auth_manager.get_cached_token()
        authenticated = token_info is not None

        return {
            "enabled": enabled,
            "authenticated": authenticated,
            "is_playing": svc._is_playing if authenticated else False,
            "current_track": svc._current_track if authenticated else None,
            "device_name": spotify_config.get("device_name", "lelamp")
        }
    except Exception as e:
        logger.error(f"Error checking Spotify status: {e}")
        return {
            "enabled": enabled,
            "authenticated": False,
            "message": f"Error: {str(e)}"
        }


@router.get("/auth/url")
async def get_spotify_auth_url():
    """Get Spotify OAuth URL for authentication."""
    _load_env()

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        return {
            "success": False,
            "error": "Spotify credentials not configured. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env file."
        }

    try:
        svc = get_spotify_service()
        if svc is None:
            return {"success": False, "error": "Spotify service not available"}

        config = get_config()
        spotify_config = config.get("spotify", {})

        # Update service config with latest env vars AND config.yaml values
        svc.config.client_id = client_id
        svc.config.client_secret = client_secret
        svc.config.redirect_uri = spotify_config.get("redirect_uri", svc.config.redirect_uri)
        svc.config.device_name = spotify_config.get("device_name", svc.config.device_name)

        auth_manager = svc._get_auth_manager()
        auth_url = auth_manager.get_authorize_url()

        return {"success": True, "auth_url": auth_url}
    except Exception as e:
        logger.error(f"Error getting Spotify auth URL: {e}")
        return {"success": False, "error": str(e)}


@router.post("/auth/code")
async def spotify_auth_with_code(request: Request):
    """Authenticate with manually entered authorization code."""
    _load_env()

    try:
        data = await request.json()
        code = data.get("code", "").strip()

        if not code:
            return {"success": False, "error": "No authorization code provided"}

        client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

        svc = get_spotify_service()
        if svc is None:
            return {"success": False, "error": "Spotify service not available"}

        # Update service config with latest env vars
        svc.config.client_id = client_id
        svc.config.client_secret = client_secret

        auth_manager = svc._get_auth_manager()
        token_info = auth_manager.get_access_token(code)

        if token_info:
            import spotipy
            svc._sp = spotipy.Spotify(auth_manager=auth_manager)
            return {"success": True, "message": "Spotify connected successfully!"}
        else:
            return {"success": False, "error": "Failed to exchange code for token"}

    except Exception as e:
        logger.error(f"Error authenticating with code: {e}")
        return {"success": False, "error": str(e)}


@router.get("/auth/callback")
async def spotify_auth_callback(code: str = None, error: str = None):
    """Handle Spotify OAuth callback."""
    if error:
        return HTMLResponse(content=f"""
            <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Authorization Failed</h1>
                <p>Error: {error}</p>
                <p><a href="/dashboard">Return to Dashboard</a></p>
            </body></html>
        """)

    if not code:
        return HTMLResponse(content="""
            <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>No Authorization Code</h1>
                <p><a href="/dashboard">Return to Dashboard</a></p>
            </body></html>
        """)

    try:
        _load_env()

        client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

        svc = get_spotify_service()
        if svc is None:
            raise Exception("Spotify service not available")

        # Update service config with latest env vars
        svc.config.client_id = client_id
        svc.config.client_secret = client_secret

        auth_manager = svc._get_auth_manager()
        token_info = auth_manager.get_access_token(code)

        if token_info:
            import spotipy
            svc._sp = spotipy.Spotify(auth_manager=auth_manager)

            return HTMLResponse(content="""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px; background: #121212; color: #fff;">
                    <h1 style="color: #1DB954;">Spotify Connected!</h1>
                    <p>You can now close this window and return to the dashboard.</p>
                    <p><a href="/dashboard" style="color: #1DB954;">Return to Dashboard</a></p>
                    <script>
                        setTimeout(() => { window.location.href = '/dashboard'; }, 2000);
                    </script>
                </body></html>
            """)
        else:
            raise Exception("Failed to get token")

    except Exception as e:
        logger.error(f"Spotify callback error: {e}")
        return HTMLResponse(content=f"""
            <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Authentication Error</h1>
                <p>Error: {str(e)}</p>
                <p><a href="/dashboard">Return to Dashboard</a></p>
            </body></html>
        """)


@router.post("/device-name")
async def update_raspotify_device_name(request: Request):
    """Update Raspotify device name."""
    try:
        data = await request.json()
        device_name = data.get("device_name", "").strip()

        if not device_name:
            return {"success": False, "error": "Device name cannot be empty"}

        # Update config.yaml
        config = load_config()
        if "spotify" not in config:
            config["spotify"] = {}
        config["spotify"]["device_name"] = device_name
        save_config(config)

        # Update g.CONFIG too
        if g.CONFIG:
            if "spotify" not in g.CONFIG:
                g.CONFIG["spotify"] = {}
            g.CONFIG["spotify"]["device_name"] = device_name

        # Update raspotify conf file using secure wrapper script
        try:
            update_cmd = [
                'sudo', '/usr/local/bin/update-raspotify-name.sh',
                device_name
            ]
            result = subprocess.run(update_cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                raise Exception(f"Failed to update config file: {result.stderr}")

            # Restart raspotify service
            restart_result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'raspotify'],
                capture_output=True,
                text=True,
                check=False
            )

            if restart_result.returncode != 0:
                raise Exception(f"Failed to restart raspotify: {restart_result.stderr}")

            return {
                "success": True,
                "message": f"Raspotify device name updated to '{device_name}' and service restarted"
            }

        except Exception as e:
            logger.error(f"Error updating raspotify config: {e}")
            return {
                "success": False,
                "error": f"Failed to update raspotify config. Error: {str(e)}"
            }

    except Exception as e:
        logger.error(f"Error updating device name: {e}")
        return {"success": False, "error": str(e)}


@router.post("/play")
async def spotify_play():
    """Resume playback."""
    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.start_playback(device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/pause")
async def spotify_pause():
    """Pause playback."""
    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.pause_playback(device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/next")
async def spotify_next():
    """Skip to next track."""
    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.next_track(device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/previous")
async def spotify_previous():
    """Skip to previous track."""
    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.previous_track(device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/volume")
async def spotify_volume(request: Request):
    """Set volume (0-100)."""
    data = await request.json()
    volume = data.get("volume", 50)

    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.volume(int(volume), device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/shuffle")
async def spotify_shuffle(request: Request):
    """Set shuffle state."""
    data = await request.json()
    state = data.get("state", False)

    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.shuffle(state, device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.post("/repeat")
async def spotify_repeat(request: Request):
    """Set repeat state (off, context, track)."""
    data = await request.json()
    state = data.get("state", "off")

    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            svc._sp.repeat(state, device_id=svc._device_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}


@router.get("/current")
async def spotify_current():
    """Get currently playing track."""
    svc = get_spotify_service()
    if svc and svc._sp:
        try:
            playback = svc._sp.current_playback()
            if playback:
                track = playback.get("item")
                device = playback.get("device", {})

                if track:
                    # Get album art URL (use largest available)
                    album_art = None
                    album_images = track.get("album", {}).get("images", [])
                    if album_images:
                        album_art = album_images[0]["url"]

                    return {
                        "success": True,
                        "is_playing": playback.get("is_playing", False),
                        "track_name": track.get("name"),
                        "artist": ", ".join([a["name"] for a in track.get("artists", [])]),
                        "album": track.get("album", {}).get("name"),
                        "album_art": album_art,
                        "progress_ms": playback.get("progress_ms", 0),
                        "duration_ms": track.get("duration_ms", 0),
                        "volume": device.get("volume_percent", 50),
                        "shuffle": playback.get("shuffle_state", False),
                        "repeat": playback.get("repeat_state", "off"),
                    }
            return {"success": True, "is_playing": False, "track_name": None}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Not authenticated"}
