# Party It Up! 🎉

A workflow that helps you plan and start amazing parties with themed music, lighting, and atmosphere!

## Features

- **Theme Selection**: Choose from many party types (birthdays, holidays, celebrations)
- **Scheduled Start**: Set an alarm for when the party begins
- **Automatic Music**: Plays themed Spotify playlists based on your party type
- **Party Lighting**: Dynamic RGB animations matching your party theme
- **Hands-free**: Everything happens automatically when the party alarm goes off!

## How to Use

### Starting the Workflow

Just say:
- "Let's party it up!"
- "I want to plan a party"
- "Help me throw a party"
- "Start the party workflow"

### Party Themes Supported

**Birthdays:**
- Kids birthday party
- Adult birthday celebration

**Holidays:**
- Christmas party
- New Year's Eve bash
- Halloween party
- Thanksgiving gathering
- Valentine's Day party
- St. Patrick's Day
- Easter celebration
- 4th of July BBQ

**Special Occasions:**
- Graduation party
- Wedding reception
- Baby shower
- Retirement party

**Casual Gatherings:**
- BBQ party
- Pool party
- Dinner party
- Game night
- Dance party

**Themed Parties:**
- 80s/90s throwback
- Disco party
- Tropical/Beach party
- Karaoke night
- And many more!

## Workflow Flow

```
1. User: "Let's party it up!"
   ↓
2. LeLamp: "What kind of party?"
   User: "New Year's Eve party"
   ↓
3. LeLamp: "When does it start?"
   User: "11pm tonight"
   ↓
4. LeLamp: Sets alarm, shows preview lighting
   ↓
[Workflow pauses until alarm triggers]
   ↓
5. ALARM GOES OFF!
   ↓
6. LeLamp: "IT'S PARTY TIME!" (exciting announcement)
   ↓
7. Chooses themed playlist (e.g., "NYE Dance Party")
   ↓
8. Plays music on Spotify
   ↓
9. Activates themed RGB lighting (gold sparkle for New Year)
   ↓
10. Party is ready! 🎊
```

## Custom Tools

### `get_party_playlist_suggestion(party_theme)`
Returns Spotify playlist recommendations based on the party theme.

**Example:**
```python
get_party_playlist_suggestion("christmas")
# Returns: "Christmas Hits, Holiday Party, Merry Christmas"
```

### `party_rgb_animation(party_theme)`
Creates themed RGB lighting effects matching the party atmosphere.

**Theme Examples:**
- **Birthday**: Colorful rainbow animations
- **Christmas**: Red and green alternating
- **Halloween**: Orange and purple spooky vibes
- **New Year**: Gold sparkle effects
- **Tropical**: Blue ocean waves
- **Dance**: Multi-color strobe effects

## State Variables

- `party_theme` (string): The type of party being planned
- `party_start_time` (string): When the party starts
- `playlist_selected` (boolean): Whether music has been chosen
- `alarm_id` (integer): ID of the party start alarm

## Tips

- Be specific with party times ("7pm tonight" vs "later")
- Choose themes that match your event for better playlist suggestions
- The workflow keeps running after the party starts - you can ask for song changes, volume adjustments, etc.
- RGB lighting automatically matches your party theme!

## Integration

Works with:
- ✅ Alarm Service (scheduled party start)
- ✅ Spotify (music playback and playlists)
- ✅ RGB Service (themed lighting)
- ✅ Audio Service (announcements and sound effects)

---

**Enjoy your party! 🎊🎵💡**
