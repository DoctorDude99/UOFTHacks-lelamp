import { useEffect, useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  PowerOff,
  Moon,
  Sun,
  Settings,
  Camera,
  Activity,
  Sliders,
  RefreshCw,
  ToggleLeft,
  ToggleRight,
  Hand,
  Workflow,
  Music2,
  Film,
  Lightbulb,
  Server,
  Thermometer,
  HardDrive,
  Cpu,
  Wifi,
  Globe,
  Fan,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboardApi, agentApi, motorsApi, servicesApi, danceApi, musicModifierApi, systemApi, setupApi } from '@/lib/api'
import { useTheme } from '@/lib/theme'
import { AuthHeader } from '@/lib/auth'

// Format token count for compact display (e.g., 1.2k, 45.3k, 1.2M)
function formatTokenCount(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`
  }
  return count.toString()
}

// Real-time Waveform Canvas using actual audio levels
function RealWaveformCanvas({
  bars,
  color,
  glowColor,
  active,
}: {
  bars: number[]
  color: string
  glowColor: string
  active: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const smoothBarsRef = useRef<number[]>(Array.from({ length: 16 }, () => 0))

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    const smoothBars = smoothBarsRef.current
    const barCount = smoothBars.length
    const barWidth = width / barCount - 2

    ctx.clearRect(0, 0, width, height)

    // Smooth interpolation to target values
    for (let i = 0; i < barCount; i++) {
      const target = bars[i] || 0
      smoothBars[i] = smoothBars[i] * 0.6 + target * 0.4
    }

    ctx.fillStyle = color
    ctx.shadowColor = glowColor
    ctx.shadowBlur = active ? 6 : 0

    for (let i = 0; i < barCount; i++) {
      const barHeight = Math.max(2, smoothBars[i] * height * 0.9)
      const x = i * (barWidth + 2) + 1
      const y = (height - barHeight) / 2
      const radius = barWidth / 2
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barHeight, radius)
      ctx.fill()
    }

    animationRef.current = requestAnimationFrame(draw)
  }, [bars, color, glowColor, active])

  useEffect(() => {
    animationRef.current = requestAnimationFrame(draw)
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
    }
  }, [draw])

  return <canvas ref={canvasRef} width={140} height={36} className="w-full h-full" />
}

// Simulated Waveform for TTS (no real data yet)
function SimulatedWaveformCanvas({
  active,
  color,
  glowColor,
}: {
  active: boolean
  color: string
  glowColor: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const barsRef = useRef<number[]>(Array.from({ length: 16 }, () => 0))

  const animate = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    const bars = barsRef.current
    const barCount = bars.length
    const barWidth = width / barCount - 2

    ctx.clearRect(0, 0, width, height)

    for (let i = 0; i < barCount; i++) {
      if (active) {
        const target = Math.random() * 0.8 + 0.2
        bars[i] = bars[i] * 0.7 + target * 0.3
      } else {
        bars[i] = bars[i] * 0.85 + 0.05 * 0.15
      }
    }

    ctx.fillStyle = color
    ctx.shadowColor = glowColor
    ctx.shadowBlur = active ? 6 : 0

    for (let i = 0; i < barCount; i++) {
      const barHeight = Math.max(2, bars[i] * height * 0.85)
      const x = i * (barWidth + 2) + 1
      const y = (height - barHeight) / 2
      const radius = barWidth / 2
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barHeight, radius)
      ctx.fill()
    }

    animationRef.current = requestAnimationFrame(animate)
  }, [active, color, glowColor])

  useEffect(() => {
    animationRef.current = requestAnimationFrame(animate)
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
    }
  }, [animate])

  return <canvas ref={canvasRef} width={140} height={36} className="w-full h-full" />
}

// Dual Audio Waveform - Real Mic (blue) and TTS (green) side by side
function DualAudioWaveform({
  isAgentSpeaking,
}: {
  isUserSpeaking: boolean
  isAgentSpeaking: boolean
}) {
  const [micBars, setMicBars] = useState<number[]>(Array(16).fill(0))
  const [micLevel, setMicLevel] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)

  // Connect to real-time audio WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/audio`)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setMicBars(data.bars || Array(16).fill(0))
        setMicLevel(data.level || 0)
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      // Silently handle errors
    }

    wsRef.current = ws

    return () => {
      ws.close()
    }
  }, [])

  const micActive = micLevel > 0.05

  return (
    <div className="grid grid-cols-2 gap-2">
      {/* Real Microphone Input - Blue */}
      <div className="space-y-1">
        <span className={`text-[10px] font-medium uppercase tracking-wider ${micActive ? 'text-blue-400' : 'text-muted-foreground/60'}`}>
          MIC
        </span>
        <div className="h-8 rounded-lg bg-muted/50 overflow-hidden">
          <RealWaveformCanvas
            bars={micBars}
            color={micActive ? '#3b82f6' : '#4b5563'}
            glowColor="rgba(59, 130, 246, 0.4)"
            active={micActive}
          />
        </div>
      </div>
      {/* TTS / Agent Speaking - Green (simulated for now) */}
      <div className="space-y-1">
        <span className={`text-[10px] font-medium uppercase tracking-wider ${isAgentSpeaking ? 'text-green-400' : 'text-muted-foreground/60'}`}>
          TTS
        </span>
        <div className="h-8 rounded-lg bg-muted/50 overflow-hidden">
          <SimulatedWaveformCanvas
            active={isAgentSpeaking}
            color={isAgentSpeaking ? '#22c55e' : '#4b5563'}
            glowColor="rgba(34, 197, 94, 0.4)"
          />
        </div>
      </div>
    </div>
  )
}

// LiveKit Configuration Banner
function LiveKitConfigBanner() {
  const navigate = useNavigate()

  // Fetch LiveKit status
  const { data: liveKitStatus } = useQuery({
    queryKey: ['livekit-status'],
    queryFn: setupApi.getLiveKitStatus,
    refetchInterval: 30000, // Check every 30 seconds
  })

  // Fetch agent enabled status
  const { data: agentEnabled } = useQuery({
    queryKey: ['agent-enabled'],
    queryFn: agentApi.getEnabled,
  })

  // Show banner if:
  // 1. Agent is enabled
  // 2. LiveKit is not configured (pipeline type is livekit by default)
  // 3. We have status data
  const showBanner =
    agentEnabled?.enabled &&
    liveKitStatus?.success &&
    !liveKitStatus?.configured

  if (!showBanner) return null

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-amber-600 dark:text-amber-400">
            LiveKit Cloud Not Configured
          </p>
          <p className="text-xs text-muted-foreground">
            AI agent requires LiveKit credentials to enable voice conversations
          </p>
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="border-amber-500/50 hover:bg-amber-500/10"
        onClick={() => navigate('/settings')}
      >
        Configure
      </Button>
    </div>
  )
}

export function Dashboard() {
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()

  // Set page title
  useEffect(() => {
    document.title = 'LeLamp Dashboard'
  }, [])

  // Fetch dashboard status
  const { data: status, isLoading } = useQuery({
    queryKey: ['dashboard-status'],
    queryFn: dashboardApi.getStatus,
    refetchInterval: 5000,
  })

  // Check if setup is complete or calibration is required
  useEffect(() => {
    if (status) {
      if (!status.config?.setup_complete) {
        navigate('/setup')
      } else if (status.config?.calibration_required) {
        // Redirect to setup with calibration step
        navigate('/setup?step=motor-calibration')
      }
    }
  }, [status, navigate])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-pulse flex items-center gap-3">
          <img src="/lelamp.svg" alt="LeLamp" className="h-8 w-8" />
          <span className="text-lg">Loading...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/lelamp.svg" alt="LeLamp" className="h-8 w-8" />
            <div>
              <h1 className="text-xl font-semibold">{status?.config?.name || 'LeLamp'}</h1>
              <p className="text-sm text-muted-foreground">Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/spotify')}
              title="Spotify"
            >
              <Music2 className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/animations')}
              title="Animations"
            >
              <Film className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/rgb-animations')}
              title="RGB Animations"
            >
              <Lightbulb className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/workflows')}
              title="Workflows"
            >
              <Workflow className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? (
                <Sun className="h-5 w-5" />
              ) : (
                <Moon className="h-5 w-5" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/settings')}
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </Button>
            {/* Auth status / User button */}
            <AuthHeader />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {/* LiveKit Configuration Banner */}
        <LiveKitConfigBanner />

        {/* Status Row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AgentStatusCard
            running={status?.agent?.running}
            sleeping={status?.agent?.sleeping}
          />
          <VisionCard />
          <SystemInfoCard />
        </div>

        {/* Services */}
        <ServicesCard />

        {/* Motor Control */}
        <MotorControlCard />
      </main>
    </div>
  )
}

// Agent state type for WebSocket data
interface AgentMetrics {
  state: string
  is_user_speaking: boolean
  is_agent_speaking: boolean
  running: boolean
  sleeping: boolean
  pipeline_type?: string
  latency?: {
    e2e_ms: number
    llm_ttft_ms: number
    tts_ttfa_ms: number
  }
  last_turn?: {
    e2e_ms: number
    llm_ttft_ms: number
    stt_ms: number
    tts_ttfa_ms: number
  }
  session?: {
    total_turns: number
    duration_s: number
  }
  tokens?: {
    session: number
    total: number
  }
}

// Pipeline type display names
const PIPELINE_DISPLAY_NAMES: Record<string, string> = {
  livekit: 'LiveKit + OpenAI',
  local: 'Local (Ollama)',
}

// Pipeline states for visual indicator (in order of conversation flow)
const PIPELINE_STATES = [
  { key: 'listening', label: 'Listening', activeClass: 'bg-blue-500', icon: 'ear' },
  { key: 'user_speaking', label: 'User', activeClass: 'bg-purple-500', icon: 'user' },
  { key: 'thinking', label: 'Thinking', activeClass: 'bg-yellow-500', icon: 'brain' },
  { key: 'speaking', label: 'Speaking', activeClass: 'bg-green-500', icon: 'speaker' },
] as const

// Agent Status Card
function AgentStatusCard({
  running,
  sleeping,
}: {
  running?: boolean
  sleeping?: boolean
}) {
  const queryClient = useQueryClient()
  const [agentMetrics, setAgentMetrics] = useState<AgentMetrics | null>(null)

  // Get agent enabled state from config
  const { data: enabledStatus } = useQuery({
    queryKey: ['agent-enabled'],
    queryFn: agentApi.getEnabled,
  })

  const enabled = enabledStatus?.enabled ?? false

  // WebSocket connection for agent metrics
  useEffect(() => {
    if (!enabled || !running) {
      setAgentMetrics(null)
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/agent`
    let ws: WebSocket | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl)
        ws.onmessage = (event) => {
          try {
            setAgentMetrics(JSON.parse(event.data))
          } catch {
            // Ignore parse errors
          }
        }
        ws.onclose = () => {
          reconnectTimeout = setTimeout(connect, 2000)
        }
      } catch {
        reconnectTimeout = setTimeout(connect, 2000)
      }
    }

    connect()

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) ws.close()
    }
  }, [enabled, running])

  const enableMutation = useMutation({
    mutationFn: agentApi.enable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-enabled'] })
    },
  })

  const disableMutation = useMutation({
    mutationFn: agentApi.disable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-enabled'] })
    },
  })

  const wakeMutation = useMutation({
    mutationFn: agentApi.wake,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-status'] }),
  })

  const sleepMutation = useMutation({
    mutationFn: agentApi.sleep,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-status'] }),
  })

  const poweroffMutation = useMutation({
    mutationFn: agentApi.poweroff,
  })

  const rebootMutation = useMutation({
    mutationFn: agentApi.reboot,
  })

  // Determine current state for display
  const getCurrentState = () => {
    if (!enabled) return 'disabled'
    if (!running) return 'stopped'
    if (sleeping) return 'sleeping'
    if (agentMetrics?.is_user_speaking) return 'user_speaking'
    return agentMetrics?.state || 'idle'
  }

  const currentState = getCurrentState()

  // Determine status indicator color
  const getStatusColor = () => {
    if (!enabled) return 'bg-gray-500'
    if (!running) return 'bg-red-500'
    if (sleeping) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  // Get status text
  const getStatusText = () => {
    if (!enabled) return 'Disabled'
    if (!running) return 'Stopped'
    if (sleeping) return 'Sleeping'
    return 'Active'
  }

  // Get pipeline display name
  const getPipelineDisplay = () => {
    const pipelineType = agentMetrics?.pipeline_type || 'livekit'
    return PIPELINE_DISPLAY_NAMES[pipelineType] || pipelineType
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">AI Agent</CardTitle>
          <div className="flex items-center gap-2">
            {agentMetrics?.tokens && agentMetrics.tokens.total > 0 && (
              <span className="text-xs text-muted-foreground font-mono" title={`Session: ${agentMetrics.tokens.session?.toLocaleString() || 0} | Total: ${agentMetrics.tokens.total.toLocaleString()}`}>
                {formatTokenCount(agentMetrics.tokens.session || 0)}/{formatTokenCount(agentMetrics.tokens.total)}
              </span>
            )}
            <div className={`h-2 w-2 rounded-full ${getStatusColor()}`} />
          </div>
        </div>
        <CardDescription>
          {getStatusText()}
          {enabled && (
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-muted">
              {getPipelineDisplay()}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Visual pipeline state indicator - only when running and not sleeping */}
        {enabled && running && !sleeping && (
          <div className="grid grid-cols-4 gap-1.5">
            {PIPELINE_STATES.map((state) => {
              const isActive = currentState === state.key
              return (
                <div
                  key={state.key}
                  className={`
                    flex flex-col items-center justify-center p-2 rounded-md transition-all duration-150
                    ${isActive
                      ? `${state.activeClass} text-white shadow-lg scale-105`
                      : 'bg-muted text-muted-foreground'
                    }
                  `}
                >
                  <span className={`text-lg ${isActive ? 'animate-pulse' : ''}`}>
                    {state.icon === 'ear' && '👂'}
                    {state.icon === 'user' && '🗣️'}
                    {state.icon === 'brain' && '🧠'}
                    {state.icon === 'speaker' && '🔊'}
                  </span>
                  <span className="text-[10px] font-medium mt-0.5">{state.label}</span>
                </div>
              )
            })}
          </div>
        )}

        {/* Last turn latency breakdown - show only when we have data */}
        {agentMetrics?.last_turn && agentMetrics.last_turn.e2e_ms > 0 && (
          <div className="space-y-1.5">
            <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
              <div className="bg-muted rounded p-1.5">
                <span className="text-muted-foreground block">STT</span>
                <span className="font-mono">{Math.round(agentMetrics.last_turn.stt_ms)}</span>
              </div>
              <div className="bg-muted rounded p-1.5">
                <span className="text-muted-foreground block">LLM</span>
                <span className="font-mono">{Math.round(agentMetrics.last_turn.llm_ttft_ms)}</span>
              </div>
              <div className="bg-muted rounded p-1.5">
                <span className="text-muted-foreground block">TTS</span>
                <span className="font-mono">{Math.round(agentMetrics.last_turn.tts_ttfa_ms)}</span>
              </div>
              <div className="bg-primary/10 rounded p-1.5">
                <span className="text-muted-foreground block">Total</span>
                <span className="font-mono font-medium">{Math.round(agentMetrics.last_turn.e2e_ms)}</span>
              </div>
            </div>
            {agentMetrics?.latency && agentMetrics.latency.e2e_ms > 0 && (
              <div className="text-center text-xs text-muted-foreground">
                Avg: <span className="font-mono">{Math.round(agentMetrics.latency.e2e_ms)}ms</span>
              </div>
            )}
          </div>
        )}

        {/* Dual Audio Waveform - VAD and TTS side by side */}
        {enabled && running && !sleeping && (
          <DualAudioWaveform
            isUserSpeaking={agentMetrics?.is_user_speaking ?? false}
            isAgentSpeaking={agentMetrics?.is_agent_speaking ?? false}
          />
        )}

        {/* Wake/Sleep Control - full width (only when enabled and running) */}
        {enabled && running && (
          sleeping ? (
            <Button
              onClick={() => wakeMutation.mutate()}
              disabled={wakeMutation.isPending}
              className="w-full"
            >
              <Sun className="mr-2 h-4 w-4" />
              Wake Up
            </Button>
          ) : (
            <Button
              variant="secondary"
              onClick={() => sleepMutation.mutate()}
              disabled={sleepMutation.isPending}
              className="w-full"
            >
              <Moon className="mr-2 h-4 w-4" />
              Sleep
            </Button>
          )
        )}

        {/* Enable/Disable Service + Reboot + Shutdown */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border">
          <Button
            size="sm"
            variant={enabled ? 'outline' : 'default'}
            onClick={() => (enabled ? disableMutation : enableMutation).mutate()}
            disabled={enableMutation.isPending || disableMutation.isPending}
          >
            {enabled ? 'Disable' : 'Enable'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (confirm('Are you sure you want to reboot the Raspberry Pi?')) {
                rebootMutation.mutate()
              }
            }}
            disabled={rebootMutation.isPending}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Reboot
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              if (confirm('Are you sure you want to shut down the Raspberry Pi?')) {
                poweroffMutation.mutate()
              }
            }}
            disabled={poweroffMutation.isPending}
          >
            <PowerOff className="h-4 w-4 mr-1" />
            Shutdown
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// Face stats type for WebSocket data
interface FaceStats {
  fps: number
  face_detected: boolean
  position: [number, number]
  size: number
  head_pose?: {
    pitch: number
    yaw: number
    roll: number
  }
}

// Vision Card - Shows live camera stream when vision service is enabled
function VisionCard() {
  const [faceStats, setFaceStats] = useState<FaceStats | null>(null)

  const { data: servicesData } = useQuery({
    queryKey: ['services-status'],
    queryFn: servicesApi.getStatus,
    refetchInterval: 5000,
  })

  const isVisionEnabled = servicesData?.services?.vision?.enabled
  const isFaceTrackingEnabled = servicesData?.services?.face_tracking?.enabled

  // Show face detection boxes only when face tracking is enabled
  const showBoxes = isFaceTrackingEnabled

  // WebSocket connection for face stats
  useEffect(() => {
    if (!isFaceTrackingEnabled) {
      setFaceStats(null)
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/stats`
    let ws: WebSocket | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl)
        ws.onmessage = (event) => {
          try {
            setFaceStats(JSON.parse(event.data))
          } catch {
            // Ignore parse errors
          }
        }
        ws.onclose = () => {
          reconnectTimeout = setTimeout(connect, 2000)
        }
      } catch {
        reconnectTimeout = setTimeout(connect, 2000)
      }
    }

    connect()

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) ws.close()
    }
  }, [isFaceTrackingEnabled])

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Vision</CardTitle>
          <div className="flex items-center gap-2">
            {isFaceTrackingEnabled && faceStats && (
              <span className="text-xs font-mono text-muted-foreground">
                {faceStats.fps?.toFixed(0)} fps
              </span>
            )}
            <div
              className={`h-2 w-2 rounded-full ${
                isVisionEnabled ? 'bg-green-500' : 'bg-muted'
              }`}
            />
          </div>
        </div>
        <CardDescription>
          {isVisionEnabled
            ? isFaceTrackingEnabled
              ? faceStats?.face_detected
                ? 'Face detected'
                : 'No face detected'
              : 'Camera active'
            : 'Enable Vision in Services'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isVisionEnabled ? (
          <>
            <div className="relative aspect-video bg-muted rounded-lg overflow-hidden">
              <img
                src={`/video_feed?show_box=${showBoxes}`}
                alt="Camera feed"
                className="w-full h-full object-cover"
              />
            </div>
            {/* Face tracking stats - show when tracking enabled */}
            {isFaceTrackingEnabled && (
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="bg-muted rounded p-1.5">
                  <span className="text-muted-foreground block">X</span>
                  <span className="font-mono font-medium">
                    {faceStats?.face_detected
                      ? (faceStats.position?.[0] ?? 0).toFixed(2)
                      : '—'}
                  </span>
                </div>
                <div className="bg-muted rounded p-1.5">
                  <span className="text-muted-foreground block">Y</span>
                  <span className="font-mono font-medium">
                    {faceStats?.face_detected
                      ? (faceStats.position?.[1] ?? 0).toFixed(2)
                      : '—'}
                  </span>
                </div>
                <div className="bg-muted rounded p-1.5">
                  <span className="text-muted-foreground block">Size</span>
                  <span className="font-mono font-medium">
                    {faceStats?.face_detected
                      ? `${((faceStats.size ?? 0) * 100).toFixed(0)}%`
                      : '—'}
                  </span>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="aspect-video bg-muted rounded-lg flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Camera className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Enable Vision in Services</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Services columns config - major categories with sub-services
const SERVICE_COLUMNS = [
  { title: 'Animation', services: ['motors', 'music_mod', 'dance'] },
  { title: 'Vision', services: ['vision', 'face_tracking', 'motor_tracking'] },
  { title: 'Audio', services: ['audio', 'spotify'] },
  { title: 'RGB', services: ['rgb'] },
]

const SERVICE_LABELS: Record<string, string> = {
  motors: 'Motors',
  vision: 'Camera',
  face_tracking: 'Face Detect',
  motor_tracking: 'Face Track',
  rgb: 'LEDs',
  audio: 'Sound FX',
  spotify: 'Spotify',
  music_mod: 'Music Mod',
  dance: 'Dance',
}

// Services Card with horizontal category columns
function ServicesCard() {
  const queryClient = useQueryClient()

  const { data: servicesData } = useQuery({
    queryKey: ['services-status'],
    queryFn: servicesApi.getStatus,
    refetchInterval: 5000,
  })

  const { data: danceData } = useQuery({
    queryKey: ['dance-status'],
    queryFn: danceApi.getStatus,
    refetchInterval: 2000,
  })

  const { data: musicData } = useQuery({
    queryKey: ['music-modifier-status'],
    queryFn: musicModifierApi.getStatus,
    refetchInterval: 2000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ service, enabled }: { service: string; enabled: boolean }) =>
      servicesApi.toggle(service, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['services-status'] }),
  })

  const danceMutation = useMutation({
    mutationFn: (enabled: boolean) => (enabled ? danceApi.enable() : danceApi.disable()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dance-status'] }),
  })

  const musicMutation = useMutation({
    mutationFn: (enabled: boolean) => (enabled ? musicModifierApi.enable() : musicModifierApi.disable()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music-modifier-status'] }),
  })

  const configServices = servicesData?.services || {}

  const getServiceState = (key: string) => {
    if (key === 'music_mod') return musicData?.enabled ?? false
    if (key === 'dance') return danceData?.dance_mode ?? false
    return configServices[key]?.enabled ?? false
  }

  const toggleService = (key: string) => {
    if (key === 'music_mod') {
      musicMutation.mutate(!musicData?.enabled)
    } else if (key === 'dance') {
      danceMutation.mutate(!danceData?.dance_mode)
    } else {
      toggleMutation.mutate({ service: key, enabled: !configServices[key]?.enabled })
    }
  }

  const isPending = toggleMutation.isPending || danceMutation.isPending || musicMutation.isPending

  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Services</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-0">
        <div className="grid grid-cols-4 gap-3">
          {SERVICE_COLUMNS.map((column) => (
            <div key={column.title}>
              <div className="text-[10px] font-semibold text-[#f47a2e] uppercase tracking-wider mb-2 pb-1 border-b border-[#ffa002]/30">
                {column.title}
              </div>
              <div className="space-y-0.5">
                {column.services.map((key) => {
                  if (key !== 'music_mod' && key !== 'dance' && !configServices[key]) return null
                  const enabled = getServiceState(key)
                  return (
                    <button
                      key={key}
                      onClick={() => toggleService(key)}
                      disabled={isPending}
                      className="flex items-center justify-between w-full py-0.5 group"
                    >
                      <span className="text-xs truncate">{SERVICE_LABELS[key]}</span>
                      {enabled ? (
                        <ToggleRight className="h-4 w-4 text-green-500 flex-shrink-0" />
                      ) : (
                        <ToggleLeft className="h-4 w-4 text-muted-foreground group-hover:text-foreground flex-shrink-0" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// System Information Card
function SystemInfoCard() {
  const queryClient = useQueryClient()

  const { data: systemInfo, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  const fanAutoMutation = useMutation({
    mutationFn: systemApi.setFanAuto,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-info'] })
    },
  })

  const fanFullMutation = useMutation({
    mutationFn: () => systemApi.setFanSpeed(100),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-info'] })
    },
  })

  const isConnected = systemInfo?.connected ?? false
  const fanMode = systemInfo?.fan?.mode || 'AUTO'

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" />
            System
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-2">
            <div className="h-4 bg-muted rounded w-3/4" />
            <div className="h-4 bg-muted rounded w-1/2" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="h-4 w-4" />
              System Info
            </CardTitle>
            <div className="text-xs text-muted-foreground mt-0.5">
              {systemInfo?.device?.model?.replace('Raspberry ', '') || 'Unknown'}
            </div>
            <div className="text-[10px] text-muted-foreground/70">
              {systemInfo?.os || ''}
            </div>
          </div>
          <div className="text-right">
            {/* Connected indicator like Tailscale */}
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
                isConnected
                  ? 'bg-green-950 text-green-400 border-green-500/50'
                  : 'bg-red-950 text-red-400 border-red-500/50'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`} />
              {isConnected ? 'Connected' : 'Offline'}
            </span>
            <div className="text-xs text-[#ffa002] mt-0.5 font-mono">
              {systemInfo?.device_name || 'lelamp'}
            </div>
            <div className="text-[10px] text-[#ffa002]/70 font-mono">
              SN:{systemInfo?.device?.serial || ''}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Stats Grid */}
        <div className="grid grid-cols-4 gap-2">
          {/* CPU */}
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Cpu className="h-3 w-3" />
              CPU
            </div>
            <div className="text-sm font-semibold">
              {systemInfo?.cpu_percent != null ? `${systemInfo.cpu_percent}%` : '—'}
            </div>
          </div>

          {/* Memory */}
          <div className="space-y-0.5">
            <div className="text-xs text-muted-foreground">
              RAM {systemInfo?.memory?.total_mb ? `${Math.round(systemInfo.memory.total_mb / 1024)}GB` : ''}
            </div>
            <div className="text-sm font-semibold">
              {systemInfo?.memory?.percent != null ? `${systemInfo.memory.percent}%` : '—'}
            </div>
          </div>

          {/* Disk */}
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <HardDrive className="h-3 w-3" />
              Disk {systemInfo?.disk?.total_gb ? `${Math.round(systemInfo.disk.total_gb)}GB` : ''}
            </div>
            <div className="text-sm font-semibold">
              {systemInfo?.disk?.percent != null ? `${systemInfo.disk.percent}%` : '—'}
            </div>
          </div>

          {/* Uptime */}
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              Up
            </div>
            <div className="text-sm font-semibold">
              {systemInfo?.uptime?.formatted || '—'}
            </div>
          </div>
        </div>

        {/* Network Info Row */}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border">
          {/* Local IP */}
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Wifi className="h-3 w-3" />
              Local IP
            </div>
            <div className="font-mono text-xs">
              {systemInfo?.network?.local_ip || '—'}
            </div>
          </div>

          {/* WAN IP */}
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Globe className="h-3 w-3" />
              WAN IP
            </div>
            <div className="font-mono text-xs">
              {systemInfo?.network?.wan_ip || '—'}
            </div>
          </div>
        </div>

        {/* Temperature with Fan Toggle */}
        <div className="flex items-center justify-between pt-2 border-t border-border">
          <div className="space-y-0.5">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Thermometer className="h-3 w-3" />
              Temperature
            </div>
            <div className="text-lg font-semibold">
              {systemInfo?.temperature != null ? `${systemInfo.temperature.toFixed(1)}°C` : '—'}
            </div>
            {systemInfo?.fan?.available && (
              <div className="text-xs text-muted-foreground flex items-center gap-1">
                <Fan className="h-3 w-3" />
                {systemInfo.fan.rpm?.toLocaleString() || '—'} RPM
              </div>
            )}
          </div>
          {/* Fan Mode Toggle */}
          {systemInfo?.fan?.available && (
            <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
              <Button
                size="sm"
                variant={fanMode === 'AUTO' ? 'default' : 'ghost'}
                className="h-6 px-2 text-xs"
                onClick={() => fanAutoMutation.mutate()}
                disabled={fanAutoMutation.isPending || fanFullMutation.isPending}
              >
                Auto
              </Button>
              <Button
                size="sm"
                variant={fanMode === 'MANUAL' ? 'default' : 'ghost'}
                className="h-6 px-2 text-xs"
                onClick={() => fanFullMutation.mutate()}
                disabled={fanAutoMutation.isPending || fanFullMutation.isPending}
              >
                Full
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Motor Control Card
function MotorControlCard() {
  const queryClient = useQueryClient()
  const [manualMode, setManualMode] = useState(false)
  const [pushableMode, setPushableMode] = useState(false)

  const { data: motors } = useQuery({
    queryKey: ['motors'],
    queryFn: motorsApi.getMotors,
  })

  const { data: positions } = useQuery({
    queryKey: ['motor-positions'],
    queryFn: motorsApi.getPositions,
    refetchInterval: manualMode || pushableMode ? 500 : false,
  })

  const { data: motorStatus } = useQuery({
    queryKey: ['motor-status'],
    queryFn: motorsApi.getStatus,
    refetchInterval: 2000,
  })

  // Sync pushable mode state from server
  useEffect(() => {
    if (motorStatus?.pushable_mode !== undefined) {
      setPushableMode(motorStatus.pushable_mode)
    }
  }, [motorStatus?.pushable_mode])

  const moveMutation = useMutation({
    mutationFn: ({ motor, position }: { motor: string; position: number }) =>
      motorsApi.move(motor, position),
  })

  const manualControlMutation = useMutation({
    mutationFn: motorsApi.setManualControl,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motors'] })
      queryClient.invalidateQueries({ queryKey: ['motor-status'] })
    },
  })

  const pushableModeMutation = useMutation({
    mutationFn: motorsApi.setPushableMode,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motor-status'] })
    },
  })

  const toggleManualMode = () => {
    const newMode = !manualMode
    setManualMode(newMode)
    // Exit pushable mode if entering manual mode
    if (newMode && pushableMode) {
      setPushableMode(false)
      pushableModeMutation.mutate(false)
    }
    manualControlMutation.mutate(newMode)
  }

  const togglePushableMode = () => {
    const newMode = !pushableMode
    setPushableMode(newMode)
    // Exit manual mode if entering pushable mode
    if (newMode && manualMode) {
      setManualMode(false)
      manualControlMutation.mutate(false)
    }
    pushableModeMutation.mutate(newMode)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sliders className="h-5 w-5 text-primary" />
            <div>
              <CardTitle>Motor Control</CardTitle>
              <CardDescription>Manually control lamp motors</CardDescription>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant={pushableMode ? 'default' : 'outline'}
              size="sm"
              onClick={togglePushableMode}
              disabled={pushableModeMutation.isPending}
              title="Enable pushable mode to move lamp by hand"
            >
              <Hand className="h-4 w-4 mr-1" />
              {pushableMode ? 'Exit' : 'Pushable'}
            </Button>
            <Button
              variant={manualMode ? 'default' : 'outline'}
              size="sm"
              onClick={toggleManualMode}
              disabled={manualControlMutation.isPending}
            >
              {manualMode ? 'Exit Manual' : 'Manual'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!manualMode && !pushableMode ? (
          <p className="text-sm text-muted-foreground">
            Select a mode above to control motors.
          </p>
        ) : pushableMode ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Pushable mode active - physically move the lamp and it will hold position.
            </p>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {motors &&
                Object.entries(motors).map(([name, config]) => (
                  <div key={name} className="flex justify-between p-2 bg-muted rounded">
                    <span className="capitalize">{name.replace(/_/g, ' ')}</span>
                    <span className="text-muted-foreground">
                      {positions?.[name]?.toFixed(1) ?? config.current}°
                    </span>
                  </div>
                ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {motors &&
              Object.entries(motors).map(([name, config]) => (
                <div key={name} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium capitalize">
                      {name.replace(/_/g, ' ')}
                    </label>
                    <span className="text-sm text-muted-foreground">
                      {positions?.[name] ?? config.current}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={config.min}
                    max={config.max}
                    value={positions?.[name] ?? config.current}
                    onChange={(e) =>
                      moveMutation.mutate({
                        motor: name,
                        position: parseInt(e.target.value),
                      })
                    }
                    className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{config.min}</span>
                    <span>{config.max}</span>
                  </div>
                </div>
              ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
