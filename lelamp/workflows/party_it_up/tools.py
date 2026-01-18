from livekit.agents import function_tool
import asyncio


@function_tool
async def play_party_music(self, party_theme: str) -> str:
    """
    Play party music on Spotify based on the party theme. This will search for and
    start playing appropriate party music automatically.

    Args:
        party_theme: The type of party (e.g., "kids birthday", "christmas", "new years eve", "halloween")

    Returns:
        Confirmation that party music is now playing
    """
    print(f"LeLamp: play_party_music called with theme={party_theme}")

    theme_lower = party_theme.lower()

    # Map party themes to Spotify search queries
    search_queries = {
        # Birthday parties
        "birthday": "birthday party hits",
        "kids birthday": "kids party music",

        # Holidays
        "christmas": "christmas party hits",
        "new year": "new years eve party",
        "new years eve": "new years eve party",
        "halloween": "halloween party music",
        "thanksgiving": "thanksgiving dinner music",
        "valentine": "valentines day party",
        "st patrick": "st patricks day party",
        "easter": "easter celebration",
        "fourth of july": "4th of july bbq hits",

        # Special occasions
        "graduation": "graduation party hits",
        "wedding": "wedding reception music",
        "baby shower": "baby shower music",
        "retirement": "celebration hits",

        # Casual gatherings
        "casual": "chill party vibes",
        "bbq": "summer bbq hits",
        "pool party": "pool party mix",
        "dinner party": "dinner party jazz",
        "game night": "fun background music",

        # Dance parties
        "dance": "dance party hits",
        "disco": "disco party classics",
        "80s": "80s party hits",
        "90s": "90s party mix",

        # Themed parties
        "tropical": "tropical party vibes",
        "beach": "beach party hits",
        "karaoke": "karaoke party hits",
        "rock": "rock party anthems",
        "country": "country party hits",
        "latin": "latin party reggaeton",
    }

    # Find best matching search query
    search_query = None
    for key, query in search_queries.items():
        if key in theme_lower:
            search_query = query
            break

    # Default to general party music if no match
    if not search_query:
        search_query = f"{party_theme} party music"

    # Try to play using Spotify service
    try:
        if hasattr(self, 'spotify_service') and self.spotify_service and self.spotify_service._sp:
            success = self.spotify_service.play_search(search_query)
            if success:
                # Give it a moment to start
                await asyncio.sleep(1)
                track = self.spotify_service.get_current_track()
                if track:
                    return f"Party music started! Now playing: {track['name']} by {track['artist']}"
                return f"Party music started! Playing {search_query}"
            else:
                return f"Couldn't find party music for '{party_theme}'. Try asking me to play specific music."
        else:
            return "Spotify is not connected. Please set up Spotify first to play party music."
    except Exception as e:
        print(f"Error playing party music: {e}")
        return f"Error playing party music: {str(e)}"


@function_tool
async def party_rgb_animation(self, party_theme: str) -> str:
    """
    Create dynamic RGB animations that match the party theme. Different themes get
    different color schemes and animation patterns.

    Args:
        party_theme: The type of party (e.g., "birthday", "christmas", "halloween")

    Returns:
        Confirmation that party lighting has been activated
    """
    from lelamp.globals import rgb_service

    print(f"LeLamp: party_rgb_animation called with theme={party_theme}")

    theme_lower = party_theme.lower()

    # Map themes to RGB animations and colors
    if "birthday" in theme_lower or "celebration" in theme_lower:
        # Colorful rainbow party vibes
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "party",
                "color": (255, 100, 200)  # Bright pink/magenta
            })
        return "Party lights activated! Colorful celebration mode with rainbow animations!"

    elif "christmas" in theme_lower or "xmas" in theme_lower:
        # Red and green alternating
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "pulse",
                "color": (255, 0, 0)  # Red, will alternate with green
            })
        return "Christmas party lights activated! Festive red and green colors!"

    elif "halloween" in theme_lower:
        # Orange and purple spooky vibes
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "spooky",
                "color": (255, 100, 0)  # Orange
            })
        return "Halloween party lights activated! Spooky orange and purple vibes!"

    elif "new year" in theme_lower:
        # Gold and silver sparkle
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "sparkle",
                "color": (255, 215, 0)  # Gold
            })
        return "New Year's party lights activated! Sparkling gold celebration mode!"

    elif "valentine" in theme_lower:
        # Romantic red and pink
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "pulse",
                "color": (255, 20, 60)  # Deep pink/red
            })
        return "Valentine's party lights activated! Romantic red and pink glow!"

    elif "st patrick" in theme_lower or "irish" in theme_lower:
        # Green party vibes
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "wave",
                "color": (0, 255, 0)  # Bright green
            })
        return "St. Patrick's party lights activated! Lucky green vibes!"

    elif "tropical" in theme_lower or "beach" in theme_lower or "pool" in theme_lower:
        # Blue and turquoise ocean vibes
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "wave",
                "color": (0, 200, 255)  # Turquoise
            })
        return "Tropical party lights activated! Cool ocean blue waves!"

    elif "dance" in theme_lower or "disco" in theme_lower:
        # Multi-color strobe/party effect
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "party",
                "color": (255, 0, 255)  # Magenta
            })
        return "Dance party lights activated! Strobing multi-color disco vibes!"

    else:
        # Default party animation - colorful and energetic
        if rgb_service:
            rgb_service.dispatch("animation", {
                "name": "party",
                "color": (255, 150, 0)  # Orange
            })
        return "Party lights activated! Energetic multi-color party mode!"
