import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Mic,
  Volume2,
  VolumeX,
  Activity,
  Clock,
  RefreshCw,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

// Microphone service status type
interface MicServiceStatus {
  success: boolean
  available: boolean
  running?: boolean
  vad_available?: boolean
  speech_active?: boolean
  gate_closed?: boolean
  current_rms?: number
  vad_threshold?: number
  barge_in_threshold?: number
  gate_release_time?: number
  message?: string
}

// Microphone config from main config
interface MicConfig {
  vad_mode?: 'server' | 'local'
  gate_release_time?: number
  barge_in_threshold?: number
  echo_gate_threshold?: number
  local_vad_threshold?: number
  server_vad_threshold?: number
  server_silence_duration_ms?: number
  debug_logging?: boolean
}

export function MicrophoneSettings() {
  // Fetch microphone service status
  const { data: micStatus, refetch: refetchStatus } = useQuery<MicServiceStatus>({
    queryKey: ['mic-service-status'],
    queryFn: async () => {
      const res = await fetch('/api/v1/setup/audio/microphone-service/status')
      return res.json()
    },
    refetchInterval: 1000, // Poll every second for live status
  })

  // Fetch config for initial values
  const { data: configData } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await fetch('/api/v1/dashboard/settings')
      return res.json()
    },
  })

  const micConfig: MicConfig = configData?.config?.microphone || {}

  // Local state for sliders
  const [gateReleaseTime, setGateReleaseTime] = useState(0.5)
  const [bargeInThreshold, setBargeInThreshold] = useState(0.2)
  const [localVadThreshold, setLocalVadThreshold] = useState(0.5)
  const [debugLogging, setDebugLogging] = useState(false)
  const [vadMode, setVadMode] = useState<'server' | 'local'>('server')
  const [restartRequired, setRestartRequired] = useState(false)

  // Sync from live service status (more accurate than config file)
  // Only sync once on initial load to avoid fighting with user input
  const [initialized, setInitialized] = useState(false)
  useEffect(() => {
    if (initialized) return

    // Try to initialize from live service first (most accurate)
    if (micStatus?.available && micStatus?.running) {
      if (micStatus.gate_release_time !== undefined) {
        setGateReleaseTime(micStatus.gate_release_time)
      }
      if (micStatus.barge_in_threshold !== undefined) {
        setBargeInThreshold(micStatus.barge_in_threshold)
      }
      if (micStatus.vad_threshold !== undefined) {
        setLocalVadThreshold(micStatus.vad_threshold)
      }
      // These only come from config
      if (micConfig?.debug_logging !== undefined) {
        setDebugLogging(micConfig.debug_logging)
      }
      if (micConfig?.vad_mode !== undefined) {
        setVadMode(micConfig.vad_mode)
      }
      setInitialized(true)
      return
    }

    // Fall back to config if service not available but config is loaded
    if (configData?.config?.microphone) {
      const mc = configData.config.microphone
      if (mc.gate_release_time !== undefined) {
        setGateReleaseTime(mc.gate_release_time)
      }
      if (mc.barge_in_threshold !== undefined) {
        setBargeInThreshold(mc.barge_in_threshold)
      }
      if (mc.local_vad_threshold !== undefined) {
        setLocalVadThreshold(mc.local_vad_threshold)
      }
      if (mc.debug_logging !== undefined) {
        setDebugLogging(mc.debug_logging)
      }
      if (mc.vad_mode !== undefined) {
        setVadMode(mc.vad_mode)
      }
      // Only mark initialized from config if service explicitly unavailable
      if (micStatus?.available === false) {
        setInitialized(true)
      }
    }
  }, [micStatus, micConfig, initialized, configData])

  // Debounced update function - updates both config and live service
  const debouncedUpdate = useCallback(
    (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      return async (updates: Partial<MicConfig>) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(async () => {
          try {
            // Update config file for persistence
            await fetch('/api/v1/dashboard/settings/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ microphone: updates }),
            })

            // Also update live service for real-time effect
            if (updates.local_vad_threshold !== undefined) {
              await fetch(`/api/v1/setup/audio/microphone-service/vad-threshold?threshold=${updates.local_vad_threshold}`, {
                method: 'POST',
              })
            }
            if (updates.barge_in_threshold !== undefined) {
              await fetch(`/api/v1/setup/audio/microphone-service/barge-in-threshold?threshold=${updates.barge_in_threshold}`, {
                method: 'POST',
              })
            }
            if (updates.gate_release_time !== undefined) {
              await fetch(`/api/v1/setup/audio/microphone-service/gate-release-time?seconds=${updates.gate_release_time}`, {
                method: 'POST',
              })
            }
            if (updates.debug_logging !== undefined) {
              await fetch(`/api/v1/setup/audio/microphone-service/debug-logging?enabled=${updates.debug_logging}`, {
                method: 'POST',
              })
            }
          } catch (e) {
            console.error('Microphone settings update failed:', e)
          }
        }, 200) // Faster response for real-time tuning
      }
    })(),
    []
  )

  const handleGateReleaseChange = (value: number) => {
    setGateReleaseTime(value)
    debouncedUpdate({ gate_release_time: value })
  }

  const handleBargeInChange = (value: number) => {
    setBargeInThreshold(value)
    debouncedUpdate({ barge_in_threshold: value })
  }

  const handleLocalVadChange = (value: number) => {
    setLocalVadThreshold(value)
    debouncedUpdate({ local_vad_threshold: value })
  }

  const handleDebugLoggingChange = (enabled: boolean) => {
    setDebugLogging(enabled)
    debouncedUpdate({ debug_logging: enabled })
  }

  const handleVadModeChange = async (mode: 'server' | 'local') => {
    setVadMode(mode)
    // Save to config (requires restart to take effect)
    await fetch('/api/v1/dashboard/settings/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ microphone: { vad_mode: mode } }),
    })
    setRestartRequired(true)
  }

  // Status indicators
  const isRunning = micStatus?.running ?? false
  const speechActive = micStatus?.speech_active ?? false
  const currentRms = micStatus?.current_rms ?? 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Mic className="h-4 w-4" />
          Microphone VAD
          {/* Status indicator */}
          <span className={`ml-auto text-xs px-2 py-0.5 rounded flex items-center gap-1 ${
            isRunning
              ? 'bg-green-500/10 text-green-500'
              : 'bg-amber-500/10 text-amber-500'
          }`}>
            {isRunning ? 'Running' : 'Stopped'}
          </span>
        </CardTitle>
        <CardDescription>Voice detection and echo cancellation tuning</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Live Status Display */}
        <div className="grid grid-cols-4 gap-2 p-2 rounded-lg bg-muted/50 text-xs">
          <div className="text-center">
            <div className="text-muted-foreground">VAD Mode</div>
            <div className={`font-medium ${micStatus?.vad_available ? 'text-green-500' : 'text-amber-500'}`}>
              {micStatus?.vad_available ? 'Silero' : 'RMS'}
            </div>
          </div>
          <div className="text-center">
            <div className="text-muted-foreground">Gate</div>
            <div className={`font-medium ${micStatus?.gate_closed ? 'text-red-500' : 'text-green-500'}`}>
              {micStatus?.gate_closed ? (
                <span className="flex items-center justify-center gap-1"><VolumeX className="h-3 w-3" /> Muted</span>
              ) : (
                <span className="flex items-center justify-center gap-1"><Volume2 className="h-3 w-3" /> Open</span>
              )}
            </div>
          </div>
          <div className="text-center">
            <div className="text-muted-foreground">Speech</div>
            <div className={`font-medium ${speechActive ? 'text-primary' : 'text-muted-foreground'}`}>
              {speechActive ? 'Detected' : 'Silent'}
            </div>
          </div>
          <div className="text-center">
            <div className="text-muted-foreground">RMS</div>
            <div className="font-mono">{currentRms.toFixed(4)}</div>
          </div>
        </div>

        {/* Warning if using fallback VAD */}
        {micStatus?.available && !micStatus?.vad_available && (
          <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-600">
            <strong>Note:</strong> Using RMS fallback VAD (PyTorch/Silero not available).
            Speech detection is less accurate - adjust Barge-in Threshold to tune.
          </div>
        )}

        {/* RMS Level Bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground flex items-center gap-1">
              <Activity className="h-3 w-3" /> Mic Level
            </span>
            <span className="font-mono">{(currentRms * 100).toFixed(1)}%</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-100 ${
                currentRms > bargeInThreshold ? 'bg-green-500' :
                currentRms > 0.01 ? 'bg-primary' : 'bg-muted-foreground/30'
              }`}
              style={{ width: `${Math.min(100, currentRms * 500)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0</span>
            <span className="text-amber-500">Barge-in: {bargeInThreshold}</span>
            <span>1</span>
          </div>
        </div>

        {/* VAD Mode Toggle */}
        <div className="border-t pt-4 space-y-3">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Voice Activity Detection
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleVadModeChange('local')}
              className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
                vadMode === 'local'
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-input hover:border-primary/50'
              }`}
            >
              <div className="font-medium">Local (Silero)</div>
              <div className="text-xs text-muted-foreground">Runs on device</div>
            </button>
            <button
              onClick={() => handleVadModeChange('server')}
              className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
                vadMode === 'server'
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-input hover:border-primary/50'
              }`}
            >
              <div className="font-medium">Server (Cloud)</div>
              <div className="text-xs text-muted-foreground">Lower latency</div>
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            {vadMode === 'local'
              ? 'Local VAD prevents echo from triggering. Better for speakers near mic.'
              : 'Server VAD is faster but may be triggered by speaker echo.'}
          </p>
          {restartRequired && (
            <p className="text-xs text-amber-500">
              Restart required for VAD mode change to take effect.
            </p>
          )}
        </div>

        <div className="border-t pt-4 space-y-4">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Local Gating (Echo Prevention)
          </div>

          {/* Gate Release Time */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="gate-release" className="text-sm flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Gate Release Delay
              </Label>
              <span className="text-sm font-mono text-muted-foreground">{gateReleaseTime.toFixed(2)}s</span>
            </div>
            <input
              id="gate-release"
              type="range"
              min={0.1}
              max={1.5}
              step={0.05}
              value={gateReleaseTime}
              onChange={(e) => handleGateReleaseChange(parseFloat(e.target.value))}
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <p className="text-xs text-muted-foreground">
              How long to wait after AI stops speaking before unmuting mic. Increase if AI cuts itself off.
            </p>
          </div>

          {/* Barge-in Threshold */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="barge-in" className="text-sm">Barge-in Threshold</Label>
              <span className="text-sm font-mono text-muted-foreground">{bargeInThreshold.toFixed(2)}</span>
            </div>
            <input
              id="barge-in"
              type="range"
              min={0.05}
              max={0.5}
              step={0.01}
              value={bargeInThreshold}
              onChange={(e) => handleBargeInChange(parseFloat(e.target.value))}
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <p className="text-xs text-muted-foreground">
              How loud you need to speak to interrupt AI. Increase if false interrupts occur.
            </p>
          </div>

          {/* Local VAD Threshold */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="local-vad" className="text-sm">Local VAD Threshold</Label>
              <span className="text-sm font-mono text-muted-foreground">{localVadThreshold.toFixed(2)}</span>
            </div>
            <input
              id="local-vad"
              type="range"
              min={0.1}
              max={0.9}
              step={0.05}
              value={localVadThreshold}
              onChange={(e) => handleLocalVadChange(parseFloat(e.target.value))}
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <p className="text-xs text-muted-foreground">
              Silero VAD sensitivity. Higher = needs louder speech to detect.
            </p>
          </div>
        </div>

        {/* Debug Toggle */}
        <div className="border-t pt-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="debug-logging" className="text-sm">Debug Logging</Label>
              <p className="text-xs text-muted-foreground">Show detailed mic/VAD logs in console</p>
            </div>
            <Switch
              id="debug-logging"
              checked={debugLogging}
              onCheckedChange={handleDebugLoggingChange}
            />
          </div>
        </div>

        {/* Refresh button */}
        <div className="pt-2">
          <button
            onClick={() => refetchStatus()}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            <RefreshCw className="h-3 w-3" /> Refresh Status
          </button>
        </div>
      </CardContent>
    </Card>
  )
}
