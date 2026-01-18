# """
# Spotify function tools for LeLamp
#
# This module contains Spotify control function tools including:
# - Play/pause/skip controls
# - Search and play music
# - Volume control
# - Queue management
# - Playback info
# """
#
# import logging
# import os
# from typing import Optional, Tuple
# from lelamp.service.agent.tools import Tool
#
#
# def _check_spotify_enabled() -> Tuple[bool, str]:
#     """
#     Check if Spotify is properly enabled and configured.
#
#     Returns:
#         Tuple of (is_enabled, error_message)
#         If enabled, returns (True, "")
#         If disabled, returns (False, "reason why")
#     """
#     from lelamp.globals import CONFIG
#
#     # Check config enable flag
#     spotify_config = CONFIG.get("spotify", {})
#     if not spotify_config.get("enabled", False):
#         return False, "Spotify is disabled in config. Set spotify.enabled: true in config.yaml"
#
#     # Check for credentials in environment
#     client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
#     client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
#
#     if not client_id or not client_secret:
#         return False, "Spotify credentials not found. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env"
#
#     return True, ""
#
#
# class SpotifyFunctions:
#     """Mixin class providing Spotify control function tools"""
#
#     @Tool.register_tool
#     async def spotify_play(self, query: Optional[str] = None) -> str:
#         """
#         Play music on Spotify! Use this when users ask to play music, songs, artists,
#         albums, or playlists. If no query is provided, resumes the current playback.
#
#         Examples:
#         - "Play some jazz" -> spotify_play("jazz")
#         - "Play Bohemian Rhapsody" -> spotify_play("bohemian rhapsody")
#         - "Play Taylor Swift" -> spotify_play("taylor swift")
#         - "Resume the music" -> spotify_play()
#
#         Args:
#             query: Optional search query - song name, artist, genre, or playlist.
#                    If None, resumes current playback.
#
#         Returns:
#             Confirmation of what's playing
#         """
#         print(f"LeLamp: spotify_play called with query: {query}")
#         try:
#             # Check if Spotify is enabled and configured
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized. Run: uv run main.py --spotify-auth"
#
#             if not self.spotify_service._sp:
#                 return "Spotify is not authenticated. Run: uv run main.py --spotify-auth"
#
#             if query:
#                 # Search and play
#                 if self.spotify_service.play_search(query):
#                     # Start dancing animation and music modifier
#                     if hasattr(self, 'animation_service') and self.animation_service:
#                         self.animation_service.dispatch("play", "dancing")
#                         self.animation_service.enable_modifier("music")
#                     # Wait a moment for playback to fully start before getting track info
#                     import asyncio
#                     await asyncio.sleep(0.5)
#                     # Get what's now playing
#                     track = self.spotify_service.get_current_track()
#                     if track:
#                         return f"Now playing: {track['name']} by {track['artist']}"
#                     return f"Playing results for: {query}"
#                 else:
#                     return f"Couldn't find anything for: {query}"
#             else:
#                 # Resume playback
#                 if self.spotify_service.play():
#                     # Start dancing animation and music modifier
#                     if hasattr(self, 'animation_service') and self.animation_service:
#                         self.animation_service.dispatch("play", "dancing")
#                         self.animation_service.enable_modifier("music")
#                     track = self.spotify_service.get_current_track()
#                     if track:
#                         return f"Resumed: {track['name']} by {track['artist']}"
#                     return "Resumed playback"
#                 else:
#                     return "Couldn't resume playback. Try playing something specific."
#
#         except Exception as e:
#             return f"Error playing music: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_pause(self) -> str:
#         """
#         Pause Spotify playback. Use when users say "pause", "stop the music",
#         "pause spotify", etc.
#
#         Returns:
#             Confirmation that music is paused
#         """
#         print("LeLamp: spotify_pause called")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.pause():
#                 return "Music paused"
#             else:
#                 return "Couldn't pause - nothing might be playing"
#
#         except Exception as e:
#             return f"Error pausing: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_next(self) -> str:
#         """
#         Skip to the next track. Use when users say "next song", "skip",
#         "skip this", "next track", etc.
#
#         Returns:
#             Info about the new track
#         """
#         print("LeLamp: spotify_next called")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.next_track():
#                 # Wait a moment for track to change
#                 import asyncio
#                 await asyncio.sleep(0.5)
#                 track = self.spotify_service.get_current_track()
#                 if track:
#                     return f"Skipped to: {track['name']} by {track['artist']}"
#                 return "Skipped to next track"
#             else:
#                 return "Couldn't skip track"
#
#         except Exception as e:
#             return f"Error skipping: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_previous(self) -> str:
#         """
#         Go back to the previous track. Use when users say "previous song",
#         "go back", "last song", "previous track", etc.
#
#         Returns:
#             Info about the track
#         """
#         print("LeLamp: spotify_previous called")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.previous_track():
#                 import asyncio
#                 await asyncio.sleep(0.5)
#                 track = self.spotify_service.get_current_track()
#                 if track:
#                     return f"Back to: {track['name']} by {track['artist']}"
#                 return "Went to previous track"
#             else:
#                 return "Couldn't go back"
#
#         except Exception as e:
#             return f"Error going back: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_current(self) -> str:
#         """
#         Get info about what's currently playing. Use when users ask
#         "what's playing?", "what song is this?", "who sings this?", etc.
#
#         Returns:
#             Current track info including song name, artist, and album
#         """
#         print("LeLamp: spotify_current called")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             track = self.spotify_service.get_current_track()
#             if track:
#                 return f"Now playing: '{track['name']}' by {track['artist']} from the album '{track['album']}'"
#             else:
#                 state = self.spotify_service.get_playback_state()
#                 if state and not state.get('is_playing'):
#                     return "Spotify is paused. Nothing currently playing."
#                 return "Nothing is currently playing on Spotify"
#
#         except Exception as e:
#             return f"Error getting current track: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_volume(self, volume_percent: int) -> str:
#         """
#         Set Spotify playback volume. Use when users want to adjust music volume
#         specifically (not system volume). "Turn up the music", "lower spotify volume", etc.
#
#         Note: This controls Spotify's volume, not the system speaker volume.
#         Use set_volume() for system volume.
#
#         Args:
#             volume_percent: Volume level 0-100
#
#         Returns:
#             Confirmation of new volume level
#         """
#         print(f"LeLamp: spotify_volume called with volume: {volume_percent}")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             volume_percent = max(0, min(100, volume_percent))
#             if self.spotify_service.set_volume(volume_percent):
#                 return f"Spotify volume set to {volume_percent}%"
#             else:
#                 return "Couldn't set Spotify volume"
#
#         except Exception as e:
#             return f"Error setting volume: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_shuffle(self, enabled: bool) -> str:
#         """
#         Turn shuffle on or off. Use when users say "shuffle", "turn on shuffle",
#         "play randomly", "turn off shuffle", etc.
#
#         Args:
#             enabled: True to enable shuffle, False to disable
#
#         Returns:
#             Confirmation of shuffle state
#         """
#         print(f"LeLamp: spotify_shuffle called with enabled: {enabled}")
#         try:
#             is_enabled, error_msg = _check_spotify_enabled()
#             if not is_enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.shuffle(enabled):
#                 return f"Shuffle {'enabled' if enabled else 'disabled'}"
#             else:
#                 return "Couldn't change shuffle setting"
#
#         except Exception as e:
#             return f"Error setting shuffle: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_play_playlist(self, playlist_name: str) -> str:
#         """
#         Play a specific playlist. Searches user's playlists first, then Spotify.
#         Use when users ask to play a playlist by name.
#
#         Examples:
#         - "Play my chill playlist" -> spotify_play_playlist("chill")
#         - "Play Discover Weekly" -> spotify_play_playlist("discover weekly")
#
#         Args:
#             playlist_name: Name of the playlist to play
#
#         Returns:
#             Confirmation of playlist playing
#         """
#         print(f"LeLamp: spotify_play_playlist called with: {playlist_name}")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.play_playlist(playlist_name):
#                 # Start dancing animation and music modifier
#                 if hasattr(self, 'animation_service') and self.animation_service:
#                     self.animation_service.dispatch("play", "dancing")
#                     self.animation_service.enable_modifier("music")
#                 return f"Playing playlist: {playlist_name}"
#             else:
#                 return f"Couldn't find playlist: {playlist_name}"
#
#         except Exception as e:
#             return f"Error playing playlist: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_play_liked(self) -> str:
#         """
#         Play the user's liked/saved songs. Use when users say
#         "play my liked songs", "play my favorites", "play my saved music", etc.
#
#         Returns:
#             Confirmation that liked songs are playing
#         """
#         print("LeLamp: spotify_play_liked called")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             if self.spotify_service.play_liked_songs():
#                 # Start dancing animation and music modifier
#                 if hasattr(self, 'animation_service') and self.animation_service:
#                     self.animation_service.dispatch("play", "dancing")
#                     self.animation_service.enable_modifier("music")
#                 return "Playing your liked songs"
#             else:
#                 return "Couldn't play liked songs"
#
#         except Exception as e:
#             return f"Error playing liked songs: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_add_to_queue(self, song_name: str) -> str:
#         """
#         Add a song to the queue. Use when users want to queue up a song
#         without interrupting what's currently playing.
#
#         Examples:
#         - "Queue up Stairway to Heaven" -> spotify_add_to_queue("stairway to heaven")
#         - "Add this to queue: Hotel California" -> spotify_add_to_queue("hotel california")
#
#         Args:
#             song_name: Name of the song to add to queue
#
#         Returns:
#             Confirmation that song was queued
#         """
#         print(f"LeLamp: spotify_add_to_queue called with: {song_name}")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             # Search for the song
#             results = self.spotify_service.search(song_name, types="track", limit=1)
#             if not results:
#                 return f"Couldn't find song: {song_name}"
#
#             track = results[0]
#             if self.spotify_service.add_to_queue(track['uri']):
#                 return f"Added to queue: {track['name']} by {track['artist']}"
#             else:
#                 return "Couldn't add to queue"
#
#         except Exception as e:
#             return f"Error adding to queue: {str(e)}"
#
#     @Tool.register_tool
#     async def spotify_search(self, query: str) -> str:
#         """
#         Search Spotify without playing. Use when users want to find music
#         but not immediately play it, or when browsing options.
#
#         Args:
#             query: Search query
#
#         Returns:
#             List of matching tracks, artists, albums
#         """
#         print(f"LeLamp: spotify_search called with: {query}")
#         try:
#             enabled, error_msg = _check_spotify_enabled()
#             if not enabled:
#                 return error_msg
#
#             if not hasattr(self, 'spotify_service') or not self.spotify_service:
#                 return "Spotify service not initialized"
#
#             results = self.spotify_service.search(query, types="track,artist,album", limit=5)
#             if not results:
#                 return f"No results for: {query}"
#
#             lines = [f"Search results for '{query}':"]
#             for item in results[:10]:
#                 item_type = item.get('type', 'track')
#                 if item_type == 'track':
#                     lines.append(f"  Track: {item['name']} by {item['artist']}")
#                 elif item_type == 'artist':
#                     lines.append(f"  Artist: {item['name']}")
#                 elif item_type == 'album':
#                     lines.append(f"  Album: {item['name']} by {item['artist']}")
#
#             return "\n".join(lines)
#
#         except Exception as e:
#             return f"Error searching: {str(e)}"
