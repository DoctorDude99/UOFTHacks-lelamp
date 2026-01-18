import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Music2,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  Shuffle,
  Repeat,
  Repeat1,
  ExternalLink,
  Check,
  AlertCircle,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { spotifyApi } from '@/lib/api'

export function Spotify() {
  const navigate = useNavigate()

  // Status query
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['spotify-status'],
    queryFn: spotifyApi.getStatus,
    refetchInterval: 5000,
  })

  // Current track query (only when authenticated)
  const { data: currentTrack } = useQuery({
    queryKey: ['spotify-current'],
    queryFn: spotifyApi.getCurrentTrack,
    enabled: status?.authenticated === true,
    refetchInterval: 2000,
  })

  // Determine what view to show
  const isEnabled = status?.enabled
  const isAuthenticated = status?.authenticated

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border shrink-0">
        <div className="px-4 py-3 flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/dashboard')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-3">
            <Music2 className="h-5 w-5 text-green-500" />
            <span className="text-lg font-semibold">Spotify</span>
          </div>
          {isAuthenticated && (
            <div className="flex items-center gap-2 ml-auto text-sm text-muted-foreground">
              <Check className="h-4 w-4 text-green-500" />
              Connected
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 p-4 max-w-2xl mx-auto w-full">
        {statusLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !isEnabled ? (
          <DisabledCard />
        ) : !isAuthenticated ? (
          <SetupCard deviceName={status?.device_name} />
        ) : (
          <PlayerCard currentTrack={currentTrack} />
        )}
      </main>
    </div>
  )
}

// Card shown when Spotify is disabled in config
function DisabledCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-yellow-500" />
          Spotify Disabled
        </CardTitle>
        <CardDescription>
          Spotify is not enabled in the configuration file.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          To enable Spotify, set <code className="bg-muted px-1 rounded">spotify.enabled: true</code> in config.yaml
          and restart the service.
        </p>
      </CardContent>
    </Card>
  )
}

// Setup card for credentials and OAuth
function SetupCard({ deviceName }: { deviceName?: string }) {
  const queryClient = useQueryClient()
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [newDeviceName, setNewDeviceName] = useState(deviceName || '')
  const [authUrl, setAuthUrl] = useState<string | null>(null)

  // Get callback URL with IP
  const { data: callbackData } = useQuery({
    queryKey: ['spotify-callback-url'],
    queryFn: spotifyApi.getCallbackUrl,
  })

  const credentialsMutation = useMutation({
    mutationFn: () => spotifyApi.saveCredentials(clientId, clientSecret),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spotify-status'] })
    },
  })

  const authUrlMutation = useMutation({
    mutationFn: spotifyApi.getAuthUrl,
    onSuccess: (data) => {
      if (data.success && data.auth_url) {
        setAuthUrl(data.auth_url)
        // Open in new tab - user will authorize and be redirected back
        window.open(data.auth_url, '_blank')
      }
    },
  })

  const deviceNameMutation = useMutation({
    mutationFn: () => spotifyApi.updateDeviceName(newDeviceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spotify-status'] })
    },
  })

  const callbackUrl = callbackData?.callback_url || ''

  return (
    <div className="space-y-4">
      {/* Step 1: Create Spotify App */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step 1: Create Spotify App</CardTitle>
          <CardDescription>
            Create an app in the Spotify Developer Dashboard
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
            <li>
              Go to{' '}
              <a
                href="https://developer.spotify.com/dashboard"
                target="_blank"
                rel="noopener noreferrer"
                className="text-green-500 hover:underline inline-flex items-center gap-1"
              >
                Spotify Developer Dashboard
                <ExternalLink className="h-3 w-3" />
              </a>
            </li>
            <li>Click <strong>Create App</strong></li>
            <li>Fill in App name and description</li>
            <li>
              <strong>Important:</strong> Add this Redirect URI:
            </li>
          </ol>
          {callbackUrl && (
            <div className="p-3 bg-muted rounded-lg font-mono text-sm break-all select-all">
              {callbackUrl}
            </div>
          )}
          <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground" start={5}>
            <li>Select <strong>Web API</strong> for APIs used</li>
            <li>Save and copy the <strong>Client ID</strong> and <strong>Client Secret</strong></li>
          </ol>
        </CardContent>
      </Card>

      {/* Step 2: Enter Credentials */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step 2: Enter Credentials</CardTitle>
          <CardDescription>
            Paste your Client ID and Client Secret from the Spotify app
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="client-id">Client ID</Label>
            <Input
              id="client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="Enter your Spotify Client ID"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="client-secret">Client Secret</Label>
            <Input
              id="client-secret"
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder="Enter your Spotify Client Secret"
            />
          </div>
          <Button
            onClick={() => credentialsMutation.mutate()}
            disabled={!clientId || !clientSecret || credentialsMutation.isPending}
          >
            {credentialsMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            Save Credentials
          </Button>
          {credentialsMutation.isSuccess && (
            <p className="text-sm text-green-500">Credentials saved!</p>
          )}
          {credentialsMutation.isError && (
            <p className="text-sm text-red-500">Failed to save credentials</p>
          )}
        </CardContent>
      </Card>

      {/* Step 3: Device Name (Optional) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step 3: Raspotify Device Name (Optional)</CardTitle>
          <CardDescription>
            Set the name of your Spotify Connect device
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="device-name">Device Name</Label>
            <Input
              id="device-name"
              value={newDeviceName}
              onChange={(e) => setNewDeviceName(e.target.value)}
              placeholder="e.g., LeLamp"
            />
          </div>
          <Button
            variant="outline"
            onClick={() => deviceNameMutation.mutate()}
            disabled={!newDeviceName || deviceNameMutation.isPending}
          >
            {deviceNameMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            Update Device Name
          </Button>
          {deviceNameMutation.isSuccess && (
            <p className="text-sm text-green-500">Device name updated!</p>
          )}
        </CardContent>
      </Card>

      {/* Step 4: OAuth */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step 4: Connect Spotify Account</CardTitle>
          <CardDescription>
            Authorize LeLamp to control your Spotify playback
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            onClick={() => authUrlMutation.mutate()}
            disabled={authUrlMutation.isPending}
            className="bg-green-600 hover:bg-green-700 w-full"
          >
            {authUrlMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Music2 className="h-4 w-4 mr-2" />
            )}
            Connect with Spotify
          </Button>
          <p className="text-xs text-muted-foreground text-center">
            This will open Spotify in a new tab. After authorizing, you'll be redirected back automatically.
          </p>
          {authUrl && (
            <p className="text-xs text-green-500 text-center">
              Authorization page opened - complete the login in the new tab
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// Player card for when authenticated
function PlayerCard({ currentTrack }: { currentTrack?: any }) {
  const queryClient = useQueryClient()
  const [volume, setVolume] = useState(currentTrack?.volume || 50)

  // Update local volume when track data changes
  useEffect(() => {
    if (currentTrack?.volume !== undefined) {
      setVolume(currentTrack.volume)
    }
  }, [currentTrack?.volume])

  const playMutation = useMutation({
    mutationFn: spotifyApi.play,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const pauseMutation = useMutation({
    mutationFn: spotifyApi.pause,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const nextMutation = useMutation({
    mutationFn: spotifyApi.next,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const prevMutation = useMutation({
    mutationFn: spotifyApi.previous,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const volumeMutation = useMutation({
    mutationFn: (vol: number) => spotifyApi.setVolume(vol),
  })

  const shuffleMutation = useMutation({
    mutationFn: (state: boolean) => spotifyApi.setShuffle(state),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const repeatMutation = useMutation({
    mutationFn: (state: string) => spotifyApi.setRepeat(state),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['spotify-current'] }),
  })

  const isPlaying = currentTrack?.is_playing
  const hasTrack = currentTrack?.track_name

  // Format time from ms to mm:ss
  const formatTime = (ms?: number) => {
    if (!ms) return '0:00'
    const seconds = Math.floor(ms / 1000)
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const progress = currentTrack?.duration_ms
    ? (currentTrack.progress_ms / currentTrack.duration_ms) * 100
    : 0

  // Cycle repeat: off -> context -> track -> off
  const cycleRepeat = () => {
    const current = currentTrack?.repeat || 'off'
    const next = current === 'off' ? 'context' : current === 'context' ? 'track' : 'off'
    repeatMutation.mutate(next)
  }

  return (
    <Card>
      <CardContent className="p-6">
        {/* Album Art & Track Info */}
        <div className="flex gap-4 mb-6">
          <div className="w-32 h-32 bg-muted rounded-lg overflow-hidden shrink-0">
            {currentTrack?.album_art ? (
              <img
                src={currentTrack.album_art}
                alt="Album art"
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Music2 className="h-12 w-12 text-muted-foreground" />
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            {hasTrack ? (
              <>
                <h2 className="text-xl font-semibold truncate">{currentTrack.track_name}</h2>
                <p className="text-muted-foreground truncate">{currentTrack.artist}</p>
                <p className="text-sm text-muted-foreground truncate">{currentTrack.album}</p>
              </>
            ) : (
              <div className="h-full flex items-center">
                <p className="text-muted-foreground">No track playing</p>
              </div>
            )}
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-4">
          <div className="h-1 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 transition-all duration-1000"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>{formatTime(currentTrack?.progress_ms)}</span>
            <span>{formatTime(currentTrack?.duration_ms)}</span>
          </div>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => shuffleMutation.mutate(!currentTrack?.shuffle)}
            className={currentTrack?.shuffle ? 'text-green-500' : ''}
          >
            <Shuffle className="h-5 w-5" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => prevMutation.mutate()}
            disabled={prevMutation.isPending}
          >
            <SkipBack className="h-6 w-6" />
          </Button>

          <Button
            size="lg"
            className="rounded-full h-14 w-14 bg-green-600 hover:bg-green-700"
            onClick={() => (isPlaying ? pauseMutation : playMutation).mutate()}
            disabled={playMutation.isPending || pauseMutation.isPending}
          >
            {isPlaying ? (
              <Pause className="h-6 w-6" />
            ) : (
              <Play className="h-6 w-6 ml-1" />
            )}
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => nextMutation.mutate()}
            disabled={nextMutation.isPending}
          >
            <SkipForward className="h-6 w-6" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={cycleRepeat}
            className={currentTrack?.repeat !== 'off' ? 'text-green-500' : ''}
          >
            {currentTrack?.repeat === 'track' ? (
              <Repeat1 className="h-5 w-5" />
            ) : (
              <Repeat className="h-5 w-5" />
            )}
          </Button>
        </div>

        {/* Volume Control */}
        <div className="flex items-center gap-3">
          <Volume2 className="h-5 w-5 text-muted-foreground shrink-0" />
          <input
            type="range"
            min={0}
            max={100}
            value={volume}
            onChange={(e) => {
              const newVol = parseInt(e.target.value)
              setVolume(newVol)
            }}
            onMouseUp={() => volumeMutation.mutate(volume)}
            onTouchEnd={() => volumeMutation.mutate(volume)}
            className="flex-1 h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-green-500"
          />
          <span className="text-sm text-muted-foreground w-8 text-right">{volume}%</span>
        </div>
      </CardContent>
    </Card>
  )
}
