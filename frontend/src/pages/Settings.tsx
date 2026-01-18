import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Settings as SettingsIcon,
  Volume2,
  Mic,
  Lamp,
  MapPin,
  Palette,
  Loader2,
  Check,
  Bot,
  Search,
  Cloud,
  AlertTriangle,
  Wrench,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { dashboardApi, themeApi, setupApi, charactersApi } from '@/lib/api'

// Location search result type
type LocationResult = {
  city: string
  region: string
  country: string
  lat: number
  lon: number
  display_name: string
  timezone?: string
}
import { AIBackendSettings } from '@/components/AIBackendSettings'
import { MicrophoneSettings } from '@/components/MicrophoneSettings'

interface ConfigData {
  id?: string
  port?: string
  volume?: number
  microphone_volume?: number
  motor_preset?: string
  motor_presets?: Record<string, unknown>
  personality?: {
    name?: string
    description?: string
    character_file?: string
    character_id?: string
  }
  location?: {
    city?: string
    region?: string
    country?: string
    timezone?: string
  }
  rgb?: {
    led_brightness?: number
    default_animation?: string
    default_color?: number[]
    led_count?: number
  }
  motors?: {
    voltage?: number
  }
}

// Helper functions to convert between hex and RGB array
function hexToRgb(hex: string): number[] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result
    ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)]
    : [0, 0, 150]
}

function rgbToHex(rgb: number[]): string {
  return '#' + rgb.map(x => x.toString(16).padStart(2, '0')).join('')
}

export function Settings() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Fetch current settings
  const { data: settingsData, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: dashboardApi.getSettings,
  })

  // Fetch available themes
  const { data: themesData } = useQuery({
    queryKey: ['themes'],
    queryFn: themeApi.getThemes,
  })

  // Fetch LiveKit status
  const { data: livekitStatus, refetch: refetchLivekit } = useQuery({
    queryKey: ['livekit-status'],
    queryFn: setupApi.getLiveKitStatus,
  })

  // Fetch available characters/personalities
  const { data: charactersData } = useQuery({
    queryKey: ['characters'],
    queryFn: charactersApi.list,
  })

  const config: ConfigData = settingsData?.config || {}

  // Local state for form values
  const [name, setName] = useState('')
  const [volume, setVolume] = useState(50)
  const [micVolume, setMicVolume] = useState(80)
  const [motorPreset, setMotorPreset] = useState('Normal')
  const [rgbBrightness, setRgbBrightness] = useState(70)
  const [defaultAnimation, setDefaultAnimation] = useState('ripple')
  const [defaultColor, setDefaultColor] = useState('#000096')

  // LiveKit state
  const [livekitUrl, setLivekitUrl] = useState('')
  const [livekitApiKey, setLivekitApiKey] = useState('')
  const [livekitApiSecret, setLivekitApiSecret] = useState('')
  const [livekitSaving, setLivekitSaving] = useState(false)
  const [livekitError, setLivekitError] = useState<string | null>(null)
  const [theme, setTheme] = useState('Lelamp')

  // Location search state
  const [locationSearch, setLocationSearch] = useState('')
  const [locationResults, setLocationResults] = useState<LocationResult[]>([])
  const [selectedLocation, setSelectedLocation] = useState<LocationResult | null>(null)
  const [isSearchingLocation, setIsSearchingLocation] = useState(false)

  // Personality state
  const [selectedCharacter, setSelectedCharacter] = useState('')

  // Sync form state when config loads
  useEffect(() => {
    if (config) {
      setName(config.personality?.name || 'LeLamp')
      setVolume(config.volume ?? 50)
      setMicVolume(config.microphone_volume ?? 80)
      setMotorPreset(config.motor_preset || 'Normal')
      setRgbBrightness(config.rgb?.led_brightness ?? 70)
      setDefaultAnimation(config.rgb?.default_animation || 'ripple')
      setDefaultColor(rgbToHex(config.rgb?.default_color || [0, 0, 150]))
      if (config.personality?.character_file) {
        setSelectedCharacter(config.personality.character_file)
      }
    }
  }, [config])

  // Sync theme state when themes data loads
  useEffect(() => {
    if (themesData?.current) {
      setTheme(themesData.current)
    }
  }, [themesData])

  // Sync LiveKit state when status loads
  useEffect(() => {
    if (livekitStatus) {
      if (livekitStatus.url) setLivekitUrl(livekitStatus.url)
      if (livekitStatus.api_key) setLivekitApiKey(livekitStatus.api_key)
    }
  }, [livekitStatus])

  const themeMutation = useMutation({
    mutationFn: (themeName: string) => themeApi.setTheme(themeName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['themes'] })
    },
  })

  const locationSearchMutation = useMutation({
    mutationFn: async (query: string) => {
      const response = await fetch(`/api/v1/setup/location/search?q=${encodeURIComponent(query)}`)
      return response.json()
    },
    onSuccess: (data) => {
      if (data.success) {
        setLocationResults(data.results || [])
      } else {
        setLocationResults([])
      }
      setIsSearchingLocation(false)
    },
    onError: () => {
      setLocationResults([])
      setIsSearchingLocation(false)
    },
  })

  const saveLocationMutation = useMutation({
    mutationFn: (location: LocationResult) => setupApi.saveLocation({
      city: location.city,
      region: location.region,
      country: location.country,
      lat: location.lat,
      lon: location.lon,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSelectedLocation(null)
      setLocationResults([])
      setLocationSearch('')
    },
  })

  const handleThemeChange = (themeName: string) => {
    setTheme(themeName)
    themeMutation.mutate(themeName)
  }

  const handleLocationSearch = () => {
    if (locationSearch.trim()) {
      setIsSearchingLocation(true)
      locationSearchMutation.mutate(locationSearch.trim())
    }
  }

  const handleSelectLocation = (location: LocationResult) => {
    setSelectedLocation(location)
    setLocationResults([])
  }

  const handleSaveLocation = () => {
    if (selectedLocation) {
      saveLocationMutation.mutate(selectedLocation)
    }
  }

  // Debounced RGB updates for live preview + auto-save
  const debouncedRgbUpdate = useCallback(
    (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      return (updates: { brightness?: number; color?: number[]; animation?: string }) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(async () => {
          try {
            // Apply live preview
            if (updates.brightness !== undefined) {
              await setupApi.setRgbBrightness(updates.brightness)
            }
            if (updates.color) {
              await setupApi.setRgbColor(updates.color[0], updates.color[1], updates.color[2])
            }
            if (updates.animation) {
              // Play the animation to preview it
              await fetch('/api/v1/dashboard/animations/play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ animation: updates.animation }),
              })
            }
            // Auto-save to config
            await dashboardApi.updateSettings({
              rgb: {
                ...(updates.brightness !== undefined && { led_brightness: updates.brightness }),
                ...(updates.color && { default_color: updates.color }),
                ...(updates.animation && { default_animation: updates.animation }),
              },
            })
          } catch (e) {
            console.error('RGB update failed:', e)
          }
        }, 150)
      }
    })(),
    []
  )

  const handleBrightnessChange = (value: number) => {
    setRgbBrightness(value)
    debouncedRgbUpdate({ brightness: value })
  }

  const handleColorChange = (hex: string) => {
    setDefaultColor(hex)
    const rgb = hexToRgb(hex)
    debouncedRgbUpdate({ color: rgb })
  }

  const handleAnimationChange = (animation: string) => {
    setDefaultAnimation(animation)
    debouncedRgbUpdate({ animation })
  }

  // Debounced auto-save for device/audio settings
  const debouncedSettingsUpdate = useCallback(
    (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      return (updates: Record<string, unknown>) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(async () => {
          try {
            await dashboardApi.updateSettings(updates)
          } catch (e) {
            console.error('Settings update failed:', e)
          }
        }, 300)
      }
    })(),
    []
  )

  const handleNameChange = (value: string) => {
    setName(value)
    debouncedSettingsUpdate({ personality: { name: value } })
  }

  const handleMotorPresetChange = (value: string) => {
    setMotorPreset(value)
    debouncedSettingsUpdate({ motor_preset: value })
  }

  const handleCharacterChange = async (characterFile: string) => {
    setSelectedCharacter(characterFile)
    try {
      await charactersApi.update(characterFile)
      // Refresh settings to get new personality info
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (error) {
      console.error('Failed to update character:', error)
    }
  }

  const handleVolumeChange = (value: number) => {
    setVolume(value)
    debouncedSettingsUpdate({ volume: value })
  }

  const handleMicVolumeChange = (value: number) => {
    setMicVolume(value)
    debouncedSettingsUpdate({ microphone_volume: value })
  }

  const handleLivekitSave = async () => {
    if (!livekitUrl || !livekitApiKey || !livekitApiSecret) {
      setLivekitError('All fields are required')
      return
    }

    setLivekitSaving(true)
    setLivekitError(null)

    try {
      const result = await setupApi.configureLiveKit({
        url: livekitUrl,
        api_key: livekitApiKey,
        api_secret: livekitApiSecret,
      })

      if (result.success) {
        refetchLivekit()
        setLivekitApiSecret('') // Clear secret after save
      } else {
        setLivekitError(result.error || 'Configuration failed')
      }
    } catch (e) {
      setLivekitError('Failed to save LiveKit configuration')
    } finally {
      setLivekitSaving(false)
    }
  }

  const motorPresets = Object.keys(config.motor_presets || { Gentle: {}, Normal: {}, Sport: {} })
  const animations = ['ripple', 'rainbow', 'pulse', 'chase', 'breathe', 'sparkle', 'solid']

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border shrink-0">
        <div className="px-4 py-3 flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/dashboard')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-3">
            <SettingsIcon className="h-5 w-5 text-primary" />
            <span className="text-lg font-semibold">Settings</span>
          </div>
        </div>
      </header>

      <main className="flex-1 p-4 max-w-6xl mx-auto w-full">
        {/* 3-column grid for settings cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Device Info - First position */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Lamp className="h-4 w-4" />
                LeLamp Device
              </CardTitle>
              <CardDescription>Device and motor settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  placeholder="LeLamp"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="personality">Personality</Label>
                <select
                  id="personality"
                  value={selectedCharacter}
                  onChange={(e) => handleCharacterChange(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
                >
                  {charactersData?.characters?.map((char) => (
                    <option key={char.file} value={char.file}>
                      {char.name}
                    </option>
                  ))}
                </select>
                {charactersData?.characters?.find(c => c.file === selectedCharacter)?.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {charactersData.characters.find(c => c.file === selectedCharacter)?.description}
                  </p>
                )}
                <p className="text-xs text-amber-500">
                  Restart required for personality changes to take effect
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground text-xs">Port</span>
                  <div className="font-mono text-xs">{config.port || '/dev/lelamp'}</div>
                </div>
                <div>
                  <span className="text-muted-foreground text-xs">Voltage</span>
                  <div>{config.motors?.voltage || 7.4}V</div>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="motor-preset">Motor Preset</Label>
                <select
                  id="motor-preset"
                  value={motorPreset}
                  onChange={(e) => handleMotorPresetChange(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
                >
                  {motorPresets.map((preset) => (
                    <option key={preset} value={preset}>
                      {preset}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  Gentle = slow, Normal = balanced, Sport = fast
                </p>
              </div>
              <div className="pt-2 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => navigate('/setup?step=motor-calibration')}
                >
                  <Wrench className="h-4 w-4 mr-2" />
                  Calibrate Motors
                </Button>
                <p className="text-xs text-muted-foreground mt-1">
                  Re-run motor calibration if positions seem off
                </p>
              </div>
            </CardContent>
          </Card>

          {/* AI Agent Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" />
                AI Agent
              </CardTitle>
              <CardDescription>Backend, API key, and voice</CardDescription>
            </CardHeader>
            <CardContent>
              <AIBackendSettings compact />
            </CardContent>
          </Card>

          {/* LiveKit Cloud Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Cloud className="h-4 w-4" />
                LiveKit Cloud
                {livekitStatus?.configured ? (
                  <span className="ml-auto text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-500 flex items-center gap-1">
                    <Check className="h-3 w-3" />
                    {livekitStatus?.service_status === 'connected' ? 'Connected' : 'Configured'}
                  </span>
                ) : (
                  <span className="ml-auto text-xs px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    Not Configured
                  </span>
                )}
              </CardTitle>
              <CardDescription>Real-time audio / video streaming</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {livekitStatus?.room_name && (
                <div className="text-xs text-muted-foreground">
                  Room: <code className="bg-muted px-1 rounded">{livekitStatus.room_name}</code>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="livekit-url">WebSocket URL</Label>
                <Input
                  id="livekit-url"
                  type="text"
                  placeholder="wss://your-project.livekit.cloud"
                  value={livekitUrl}
                  onChange={(e) => setLivekitUrl(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="livekit-api-key">API Key</Label>
                <Input
                  id="livekit-api-key"
                  type="text"
                  placeholder="APIxxxxx"
                  value={livekitApiKey}
                  onChange={(e) => setLivekitApiKey(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="livekit-api-secret">API Secret</Label>
                <Input
                  id="livekit-api-secret"
                  type="password"
                  placeholder={livekitStatus?.configured ? '••••••••' : 'Enter your API secret'}
                  value={livekitApiSecret}
                  onChange={(e) => setLivekitApiSecret(e.target.value)}
                />
              </div>
              {livekitError && (
                <p className="text-sm text-red-500 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {livekitError}
                </p>
              )}
              <Button
                onClick={handleLivekitSave}
                disabled={livekitSaving || !livekitUrl || !livekitApiKey || !livekitApiSecret}
                className="w-full"
                size="sm"
              >
                {livekitSaving ? 'Saving...' : 'Save LiveKit Configuration'}
              </Button>
              <p className="text-xs text-muted-foreground">
                Get credentials from{' '}
                <a href="https://cloud.livekit.io" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  cloud.livekit.io
                </a>
              </p>
              {livekitStatus?.configured && (
                <p className="text-xs text-muted-foreground">
                  Listen to room from desktop:{' '}
                  <a href="/api/v1/setup/livekit/viewer-token" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                    Get viewer token
                  </a>
                </p>
              )}
            </CardContent>
          </Card>

          {/* Microphone VAD Settings */}
          <MicrophoneSettings />

          {/* Audio Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Volume2 className="h-4 w-4" />
                Audio
              </CardTitle>
              <CardDescription>Volume, microphone, and sounds</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="volume">Speaker</Label>
                  <span className="text-sm text-muted-foreground">{volume}%</span>
                </div>
                <input
                  id="volume"
                  type="range"
                  min={0}
                  max={100}
                  value={volume}
                  onChange={(e) => handleVolumeChange(parseInt(e.target.value))}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="mic-volume" className="flex items-center gap-2">
                    <Mic className="h-3 w-3" />
                    Microphone
                  </Label>
                  <span className="text-sm text-muted-foreground">{micVolume}%</span>
                </div>
                <input
                  id="mic-volume"
                  type="range"
                  min={0}
                  max={100}
                  value={micVolume}
                  onChange={(e) => handleMicVolumeChange(parseInt(e.target.value))}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
              </div>
              <div className="space-y-2 pt-2 border-t">
                <Label htmlFor="theme">Sound Theme</Label>
                <select
                  id="theme"
                  value={theme}
                  onChange={(e) => handleThemeChange(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
                >
                  {(themesData?.themes || []).map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name} ({t.sound_count} sounds)
                    </option>
                  ))}
                </select>
                {themeMutation.isPending && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" /> Switching...
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* RGB Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Palette className="h-4 w-4" />
                RGB LEDs
                <span className="text-xs text-muted-foreground font-normal ml-auto">
                  {config.rgb?.led_count || 93} LEDs
                </span>
              </CardTitle>
              <CardDescription>Brightness and animation</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="brightness">Brightness</Label>
                  <span className="text-sm text-muted-foreground">{rgbBrightness}%</span>
                </div>
                <input
                  id="brightness"
                  type="range"
                  min={0}
                  max={100}
                  value={rgbBrightness}
                  onChange={(e) => handleBrightnessChange(parseInt(e.target.value))}
                  className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="default-color">Default Color</Label>
                <div className="flex items-center gap-2">
                  <input
                    id="default-color"
                    type="color"
                    value={defaultColor}
                    onChange={(e) => handleColorChange(e.target.value)}
                    className="h-10 w-12 rounded-md border border-input cursor-pointer"
                  />
                  <Input
                    value={defaultColor}
                    onChange={(e) => handleColorChange(e.target.value)}
                    placeholder="#000096"
                    className="flex-1 font-mono uppercase text-xs"
                    maxLength={7}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="animation">Animation</Label>
                <select
                  id="animation"
                  value={defaultAnimation}
                  onChange={(e) => handleAnimationChange(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
                >
                  {animations.map((anim) => (
                    <option key={anim} value={anim}>
                      {anim.charAt(0).toUpperCase() + anim.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>

          {/* Location Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <MapPin className="h-4 w-4" />
                Location
              </CardTitle>
              <CardDescription>Weather and timezone</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Current Location Display */}
              {config.location?.city && !selectedLocation && (
                <div className="p-3 rounded-lg bg-muted/50 text-sm">
                  <div className="font-medium">
                    {config.location.city}, {config.location.region}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {config.location.country} · {config.location.timezone}
                  </div>
                </div>
              )}

              {/* Selected Location (pending save) */}
              {selectedLocation && (
                <div className="p-3 rounded-lg bg-primary/10 border border-primary text-sm">
                  <div className="font-medium flex items-center gap-2">
                    <Check className="h-3 w-3 text-primary" />
                    {selectedLocation.city}, {selectedLocation.region}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {selectedLocation.country} · {selectedLocation.timezone}
                  </div>
                  <div className="flex gap-2 mt-2">
                    <Button
                      size="sm"
                      onClick={handleSaveLocation}
                      disabled={saveLocationMutation.isPending}
                    >
                      {saveLocationMutation.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : null}
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setSelectedLocation(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {/* Search Input */}
              <div className="space-y-2">
                <Label className="text-xs">Search City</Label>
                <div className="flex gap-2">
                  <Input
                    value={locationSearch}
                    onChange={(e) => setLocationSearch(e.target.value)}
                    placeholder="Enter city name..."
                    className="h-9"
                    onKeyDown={(e) => e.key === 'Enter' && handleLocationSearch()}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleLocationSearch}
                    disabled={isSearchingLocation || !locationSearch.trim()}
                    className="h-9 px-3"
                  >
                    {isSearchingLocation ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Search className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Search Results */}
              {locationResults.length > 0 && (
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {locationResults.map((loc, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSelectLocation(loc)}
                      className="w-full p-2 text-left rounded hover:bg-muted transition-colors text-sm"
                    >
                      <div className="font-medium">{loc.city}, {loc.region}</div>
                      <div className="text-xs text-muted-foreground">
                        {loc.country} · {loc.timezone}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

      </main>
    </div>
  )
}
