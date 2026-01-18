import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, ArrowLeft, Check, MapPin, User, Cog, AlertTriangle, Wifi, WifiOff, RefreshCw, SkipForward, Volume2, Mic, Camera, Lightbulb, Sun, Moon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { setupApi, calibrationApi, dashboardApi } from '@/lib/api'
import { useTheme } from '@/lib/theme'

type Step = 'welcome' | 'wifi' | 'audio' | 'camera' | 'rgb' | 'environment' | 'location' | 'personality' | 'motor-calibration' | 'complete'

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

const STEPS: Step[] = ['welcome', 'wifi', 'audio', 'camera', 'rgb', 'environment', 'location', 'personality', 'complete']
const CALIBRATION_STEPS: Step[] = ['motor-calibration', 'complete']

export function SetupWizard() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [currentStep, setCurrentStep] = useState<Step>('welcome')
  const [isCalibrationOnly, setIsCalibrationOnly] = useState(false)
  const { theme, toggleTheme } = useTheme()

  // Set page title
  useEffect(() => {
    document.title = 'LeLamp Setup Wizard'
  }, [])

  // Fetch setup status
  const { data: status } = useQuery({
    queryKey: ['setup-status'],
    queryFn: setupApi.getStatus,
  })

  // Fetch dashboard status to check calibration_required
  const { data: dashboardStatus } = useQuery({
    queryKey: ['dashboard-status'],
    queryFn: dashboardApi.getStatus,
  })

  // Check if we're in calibration-only mode (redirected from dashboard)
  useEffect(() => {
    const stepParam = searchParams.get('step')
    if (stepParam === 'motor-calibration') {
      setIsCalibrationOnly(true)
      setCurrentStep('motor-calibration')
    }
  }, [searchParams])

  // If setup is complete and no calibration needed, redirect to dashboard
  useEffect(() => {
    if (status?.setup_complete && !dashboardStatus?.config?.calibration_required && !isCalibrationOnly) {
      navigate('/dashboard')
    }
  }, [status, dashboardStatus, navigate, isCalibrationOnly])

  // Determine which step list to use
  const stepList = isCalibrationOnly ? CALIBRATION_STEPS : STEPS
  const currentIndex = stepList.indexOf(currentStep)
  const progress = stepList.length > 1 ? ((currentIndex) / (stepList.length - 1)) * 100 : 100

  const goNext = () => {
    const nextIndex = currentIndex + 1
    if (nextIndex < stepList.length) {
      setCurrentStep(stepList[nextIndex])
    }
  }

  const goBack = () => {
    if (isCalibrationOnly) {
      // In calibration-only mode, back goes to dashboard
      navigate('/dashboard')
      return
    }
    const prevIndex = currentIndex - 1
    if (prevIndex >= 0) {
      setCurrentStep(stepList[prevIndex])
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Progress bar */}
      <div className="h-1 bg-muted">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Header */}
      <header className="p-4 border-b border-border">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/lelamp.svg" alt="LeLamp" className="h-8 w-8" />
            <div>
              <h1 className="text-xl font-semibold">LeLamp Setup</h1>
              <p className="text-sm text-muted-foreground">
                Step {currentIndex + 1} of {STEPS.length}
              </p>
            </div>
          </div>
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
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 p-4">
        <div className="max-w-2xl mx-auto">
          {currentStep === 'welcome' && <WelcomeStep onNext={goNext} />}
          {currentStep === 'wifi' && <WifiStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'audio' && <AudioStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'camera' && <CameraStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'rgb' && <RGBStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'environment' && <EnvironmentStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'location' && <LocationStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'personality' && <PersonalityStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'motor-calibration' && <MotorCalibrationStep onNext={goNext} onBack={goBack} />}
          {currentStep === 'complete' && <CompleteStep isCalibrationOnly={isCalibrationOnly} />}
        </div>
      </main>
    </div>
  )
}

// Welcome Step
function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <Card>
      <CardHeader className="text-center">
        <div className="mx-auto mb-4 h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
          <img src="/lelamp.svg" alt="LeLamp" className="h-10 w-10" />
        </div>
        <CardTitle className="text-2xl">Welcome to LeLamp!</CardTitle>
        <CardDescription>
          Let's get your AI robot lamp set up. This will only take a few minutes.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex justify-center">
        <Button onClick={onNext} size="lg">
          Get Started
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </CardContent>
    </Card>
  )
}

// WiFi Network type
type WifiNetwork = {
  ssid: string
  signal: number
  security: string
  connected: boolean
}

// WiFi Step
function WifiStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [networks, setNetworks] = useState<WifiNetwork[]>([])
  const [selectedNetwork, setSelectedNetwork] = useState<WifiNetwork | null>(null)
  const [password, setPassword] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: wifiStatus } = useQuery({
    queryKey: ['wifi-status'],
    queryFn: setupApi.getWifiStatus,
  })

  // Auto-skip if already connected to WiFi (station mode) AND has internet
  useEffect(() => {
    if (wifiStatus?.success && wifiStatus.mode === "station" && wifiStatus.has_internet) {
      onNext()
    }
  }, [wifiStatus, onNext])

  const scanMutation = useMutation({
    mutationFn: setupApi.scanWifi,
    onSuccess: (data) => {
      if (data.success) {
        setNetworks(data.networks || [])
        setError(null)
      } else {
        setError(data.error || 'Scan failed')
      }
      setIsScanning(false)
    },
    onError: () => {
      setError('Failed to scan networks')
      setIsScanning(false)
    },
  })

  const connectMutation = useMutation({
    mutationFn: () => {
      if (!selectedNetwork) throw new Error('No network selected')
      return setupApi.connectWifi(selectedNetwork.ssid, password)
    },
    onSuccess: (data) => {
      if (data.success) {
        onNext()
      } else {
        setError(data.error || 'Failed to connect')
      }
    },
    onError: (err) => {
      setError(String(err))
    },
  })

  const skipMutation = useMutation({
    mutationFn: setupApi.skipWifi,
    onSuccess: () => onNext(),
  })

  const handleScan = () => {
    setIsScanning(true)
    setError(null)
    scanMutation.mutate()
  }

  // Initial scan
  useEffect(() => {
    handleScan()
  }, [])

  const getSignalIcon = (strength: number) => {
    if (strength >= 70) return <Wifi className="h-4 w-4 text-green-500" />
    if (strength >= 40) return <Wifi className="h-4 w-4 text-yellow-500" />
    return <WifiOff className="h-4 w-4 text-red-500" />
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Wifi className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>WiFi Setup</CardTitle>
            <CardDescription>Connect LeLamp to your WiFi network</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 text-red-500 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        <div className="flex items-center justify-between">
          <Label>Available Networks</Label>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleScan}
            disabled={isScanning}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${isScanning ? 'animate-spin' : ''}`} />
            {isScanning ? 'Scanning...' : 'Refresh'}
          </Button>
        </div>

        {networks.length > 0 ? (
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {networks.map((network, index) => (
              <button
                key={index}
                type="button"
                onClick={() => setSelectedNetwork(network)}
                className={`w-full p-3 text-left rounded-lg border transition-colors ${
                  selectedNetwork?.ssid === network.ssid
                    ? 'border-primary bg-primary/10'
                    : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getSignalIcon(network.signal)}
                    <span className="font-medium">{network.ssid}</span>
                    {network.connected && (
                      <span className="text-xs text-green-500">(Connected)</span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{network.security}</span>
                </div>
              </button>
            ))}
          </div>
        ) : !isScanning ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No networks found. Click Refresh to scan again.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-4">
            Scanning for networks...
          </p>
        )}

        {selectedNetwork && selectedNetwork.security !== 'Open' && (
          <div className="space-y-2">
            <Label htmlFor="wifi-password">Password for {selectedNetwork.ssid}</Label>
            <Input
              id="wifi-password"
              type="password"
              placeholder="Enter WiFi password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
        )}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => skipMutation.mutate()}
              disabled={skipMutation.isPending}
            >
              <SkipForward className="mr-2 h-4 w-4" />
              Skip (Local Only)
            </Button>
            <Button
              onClick={() => connectMutation.mutate()}
              disabled={!selectedNetwork || connectMutation.isPending}
            >
              {connectMutation.isPending ? 'Connecting...' : 'Connect'}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// =============================================================================
// Audio Step - Speaker and Microphone Testing
// =============================================================================

// Real-time Waveform Canvas using actual audio levels (same as Dashboard)
function MicWaveformCanvas({
  bars,
  active,
}: {
  bars: number[]
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

    const color = active ? '#3b82f6' : '#4b5563'
    ctx.fillStyle = color
    ctx.shadowColor = 'rgba(59, 130, 246, 0.4)'
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
  }, [bars, active])

  useEffect(() => {
    animationRef.current = requestAnimationFrame(draw)
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
    }
  }, [draw])

  return <canvas ref={canvasRef} width={280} height={48} className="w-full h-full" />
}

function AudioStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [speakerTested, setSpeakerTested] = useState(false)
  const [speakerPlaying, setSpeakerPlaying] = useState(false)
  const [micBars, setMicBars] = useState<number[]>(Array(16).fill(0))
  const [micLevel, setMicLevel] = useState(0)
  const [speakerVolume, setSpeakerVolume] = useState(50)
  const [micVolume, setMicVolume] = useState(50)
  const [error, setError] = useState<string | null>(null)
  const speakerStatusInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const volumeDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Check audio status
  const { data: audioStatus, isLoading } = useQuery({
    queryKey: ['audio-status'],
    queryFn: setupApi.getAudioStatus,
  })

  // Fetch current volume levels
  const { data: volumes } = useQuery({
    queryKey: ['audio-volumes'],
    queryFn: setupApi.getAudioVolumes,
  })

  // Update local state when volumes are fetched
  useEffect(() => {
    if (volumes?.success) {
      setSpeakerVolume(volumes.speaker_volume ?? 50)
      setMicVolume(volumes.microphone_volume ?? 50)
    }
  }, [volumes])

  // Auto-skip if no audio hardware available
  useEffect(() => {
    if (audioStatus?.success && !audioStatus.available) {
      onNext()
    }
  }, [audioStatus, onNext])

  // Connect to real-time audio WebSocket on mount for live mic visualization
  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/audio`

    const connect = () => {
      try {
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            setMicBars(data.bars || Array(16).fill(0))
            setMicLevel(data.level || 0)
          } catch {
            // Ignore parse errors
          }
        }

        ws.onerror = () => {
          // Silent error handling - will reconnect
        }

        ws.onclose = () => {
          // Attempt to reconnect after a short delay
          setTimeout(() => {
            if (wsRef.current === ws) {
              connect()
            }
          }, 2000)
        }
      } catch {
        // Silent error handling
      }
    }

    connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (speakerStatusInterval.current) {
        clearInterval(speakerStatusInterval.current)
      }
    }
  }, [])

  const testSpeakerMutation = useMutation({
    mutationFn: setupApi.testSpeaker,
    onSuccess: (data) => {
      if (data.success && data.playing) {
        setSpeakerPlaying(true)
        setSpeakerTested(true)
        setError(null)

        // Poll for playback status to know when sound finishes
        if (speakerStatusInterval.current) {
          clearInterval(speakerStatusInterval.current)
        }
        speakerStatusInterval.current = setInterval(async () => {
          try {
            const status = await setupApi.getSpeakerTestStatus()
            if (!status.playing) {
              setSpeakerPlaying(false)
              if (speakerStatusInterval.current) {
                clearInterval(speakerStatusInterval.current)
                speakerStatusInterval.current = null
              }
            }
          } catch {
            // Ignore polling errors
          }
        }, 500)

        // Auto-stop polling after 15 seconds
        setTimeout(() => {
          setSpeakerPlaying(false)
          if (speakerStatusInterval.current) {
            clearInterval(speakerStatusInterval.current)
            speakerStatusInterval.current = null
          }
        }, 15000)
      } else {
        setError(data.error || 'Speaker test failed')
      }
    },
    onError: () => setError('Failed to test speaker'),
  })

  const setVolumeMutation = useMutation({
    mutationFn: ({ speaker, mic }: { speaker?: number; mic?: number }) =>
      setupApi.setAudioVolumes(speaker, mic),
  })

  const completeMutation = useMutation({
    mutationFn: setupApi.completeAudioSetup,
    onSuccess: () => onNext(),
  })

  const skipMutation = useMutation({
    mutationFn: setupApi.skipAudioSetup,
    onSuccess: () => onNext(),
  })

  // Debounced volume change
  const handleSpeakerVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value)
    setSpeakerVolume(value)

    if (volumeDebounceRef.current) {
      clearTimeout(volumeDebounceRef.current)
    }

    volumeDebounceRef.current = setTimeout(() => {
      setVolumeMutation.mutate({ speaker: value })
    }, 50)
  }

  const handleMicVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value)
    setMicVolume(value)

    if (volumeDebounceRef.current) {
      clearTimeout(volumeDebounceRef.current)
    }

    volumeDebounceRef.current = setTimeout(() => {
      setVolumeMutation.mutate({ mic: value })
    }, 50)
  }

  const micActive = micLevel > 0.05

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Checking audio hardware...</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Volume2 className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Audio Setup</CardTitle>
            <CardDescription>Adjust volume and test your audio</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 text-red-500 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        {/* Speaker Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="flex items-center gap-2">
              <Volume2 className="h-4 w-4" />
              Speaker Volume
            </Label>
            {speakerTested && (
              <span className="text-xs text-green-500 flex items-center gap-1">
                <Check className="h-3 w-3" /> Tested
              </span>
            )}
          </div>
          <div className="flex gap-3 items-center">
            <input
              type="range"
              min="0"
              max="100"
              value={speakerVolume}
              onChange={handleSpeakerVolumeChange}
              className="flex-1 h-2 rounded-full bg-muted appearance-none cursor-pointer"
            />
            <span className="text-sm w-10 text-right">{speakerVolume}%</span>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => testSpeakerMutation.mutate()}
            disabled={testSpeakerMutation.isPending || speakerPlaying}
          >
            {testSpeakerMutation.isPending ? 'Starting...' : speakerPlaying ? 'Playing...' : 'Test Speaker'}
          </Button>
        </div>

        {/* Microphone Section */}
        <div className="space-y-3 pt-4 border-t">
          <div className="flex items-center justify-between">
            <Label className="flex items-center gap-2">
              <Mic className="h-4 w-4" />
              Microphone Volume
            </Label>
            <span className={`text-xs font-medium uppercase tracking-wider ${micActive ? 'text-blue-400' : 'text-muted-foreground/60'}`}>
              {micActive ? 'Listening' : 'Ready'}
            </span>
          </div>
          <div className="flex gap-3 items-center">
            <input
              type="range"
              min="0"
              max="100"
              value={micVolume}
              onChange={handleMicVolumeChange}
              className="flex-1 h-2 rounded-full bg-muted appearance-none cursor-pointer"
            />
            <span className="text-sm w-10 text-right">{micVolume}%</span>
          </div>

          {/* Live microphone waveform - always on */}
          <div className="space-y-2">
            <div className="h-12 rounded-lg bg-muted/50 overflow-hidden">
              <MicWaveformCanvas bars={micBars} active={micActive} />
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Speak into the microphone to see the waveform
            </p>
          </div>
        </div>

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => skipMutation.mutate()}
              disabled={skipMutation.isPending}
            >
              <SkipForward className="mr-2 h-4 w-4" />
              Skip
            </Button>
            <Button
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
            >
              Continue
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// =============================================================================
// Camera Step - Device Selection and Live Preview
// =============================================================================

// Camera device type
type CameraDevice = {
  path: string
  actual_device: string
  name: string
  type: string
  has_mic: boolean
  working: boolean
}

function CameraStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [selectedCamera, setSelectedCamera] = useState<CameraDevice | null>(null)
  const [previewActive, setPreviewActive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Check camera status
  const { data: cameraStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['camera-status'],
    queryFn: setupApi.getCameraStatus,
  })

  // Fetch camera devices
  const { data: devicesData, isLoading: devicesLoading } = useQuery({
    queryKey: ['camera-devices'],
    queryFn: setupApi.getCameraDevices,
    enabled: cameraStatus?.available,
  })

  // Auto-skip if no cameras available
  useEffect(() => {
    if (cameraStatus?.success && !cameraStatus.available) {
      onNext()
    }
  }, [cameraStatus, onNext])

  // Auto-select first working camera
  useEffect(() => {
    if (devicesData?.cameras && !selectedCamera) {
      const workingCamera = devicesData.cameras.find((c: CameraDevice) => c.working)
      if (workingCamera) {
        setSelectedCamera(workingCamera)
        setPreviewActive(true)
      }
    }
  }, [devicesData, selectedCamera])

  const selectMutation = useMutation({
    mutationFn: () => {
      if (!selectedCamera) throw new Error('No camera selected')
      return setupApi.selectCamera(selectedCamera.path, selectedCamera.type)
    },
    onSuccess: (data) => {
      if (data.success) {
        onNext()
      } else {
        setError(data.error || 'Failed to select camera')
      }
    },
    onError: () => setError('Failed to select camera'),
  })

  const skipMutation = useMutation({
    mutationFn: setupApi.skipCameraSetup,
    onSuccess: () => onNext(),
  })

  const isLoading = statusLoading || devicesLoading

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Detecting cameras...</p>
        </CardContent>
      </Card>
    )
  }

  const cameras = devicesData?.cameras || []

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Camera className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Camera Setup</CardTitle>
            <CardDescription>Select and test your camera for face tracking</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 text-red-500 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        {cameras.length === 0 ? (
          <div className="text-center py-6">
            <Camera className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No cameras detected</p>
            <p className="text-xs text-muted-foreground mt-1">
              Connect a USB camera and try again, or skip this step.
            </p>
          </div>
        ) : (
          <>
            {/* Camera Selection */}
            <div className="space-y-2">
              <Label>Select Camera</Label>
              <div className="space-y-1">
                {cameras.map((camera: CameraDevice) => (
                  <button
                    key={camera.path}
                    type="button"
                    onClick={() => {
                      setSelectedCamera(camera)
                      setPreviewActive(true)
                    }}
                    className={`w-full p-3 text-left rounded-lg border transition-colors ${
                      selectedCamera?.path === camera.path
                        ? 'border-primary bg-primary/10'
                        : 'border-border hover:border-primary/50'
                    } ${!camera.working ? 'opacity-50' : ''}`}
                    disabled={!camera.working}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium text-sm">{camera.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {camera.path}
                          {camera.has_mic && ' • Has microphone'}
                        </div>
                      </div>
                      {camera.working ? (
                        <span className="text-xs text-green-500">Working</span>
                      ) : (
                        <span className="text-xs text-red-500">Not working</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Live Preview */}
            {selectedCamera && previewActive && (
              <div className="space-y-2">
                <Label>Live Preview</Label>
                <div className="aspect-video bg-muted rounded-lg overflow-hidden relative">
                  <img
                    src={setupApi.getCameraPreviewUrl(selectedCamera.path)}
                    alt="Camera preview"
                    className="w-full h-full object-cover"
                    onError={() => setPreviewActive(false)}
                  />
                </div>
                <p className="text-xs text-muted-foreground text-center">
                  Make sure you can see yourself clearly in the preview.
                </p>
              </div>
            )}
          </>
        )}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => skipMutation.mutate()}
              disabled={skipMutation.isPending}
            >
              <SkipForward className="mr-2 h-4 w-4" />
              Skip
            </Button>
            {selectedCamera && (
              <Button
                onClick={() => selectMutation.mutate()}
                disabled={selectMutation.isPending}
              >
                {selectMutation.isPending ? 'Saving...' : 'This looks good'}
                <Check className="ml-2 h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// =============================================================================
// RGB Step - LED Testing and Brightness Control
// =============================================================================

function RGBStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [brightness, setBrightness] = useState(50)
  const [isTesting, setIsTesting] = useState(false)
  const [testCompleted, setTestCompleted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Check RGB status
  const { data: rgbStatus, isLoading } = useQuery({
    queryKey: ['rgb-status'],
    queryFn: setupApi.getRgbStatus,
  })

  // Update local brightness when fetched
  useEffect(() => {
    if (rgbStatus?.success && rgbStatus.brightness !== undefined) {
      setBrightness(rgbStatus.brightness)
    }
  }, [rgbStatus])

  // Auto-skip if no RGB LEDs configured
  useEffect(() => {
    if (rgbStatus?.success && !rgbStatus.available) {
      onNext()
    }
  }, [rgbStatus, onNext])

  const testMutation = useMutation({
    mutationFn: setupApi.testRgb,
    onMutate: () => {
      setIsTesting(true)
      setError(null)
    },
    onSuccess: (data) => {
      if (data.success) {
        setTestCompleted(true)
        // Test runs for about 2.5 seconds
        setTimeout(() => setIsTesting(false), 2500)
      } else {
        setError(data.error || 'LED test failed')
        setIsTesting(false)
      }
    },
    onError: () => {
      setError('Failed to test LEDs')
      setIsTesting(false)
    },
  })

  const setBrightnessMutation = useMutation({
    mutationFn: (value: number) => setupApi.setRgbBrightness(value),
  })

  const completeMutation = useMutation({
    mutationFn: setupApi.completeRgbSetup,
    onSuccess: (data) => {
      if (data.success) {
        onNext()
      } else {
        setError(data.error || 'Failed to complete RGB setup')
      }
    },
    onError: () => setError('Failed to complete RGB setup'),
  })

  const skipMutation = useMutation({
    mutationFn: setupApi.skipRgbSetup,
    onSuccess: (data) => {
      if (data.success) {
        onNext()
      } else {
        setError(data.error || 'Failed to skip RGB setup')
      }
    },
    onError: () => setError('Failed to skip RGB setup'),
  })

  const handleBrightnessChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value)
    setBrightness(value)
    setBrightnessMutation.mutate(value)
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Checking RGB LEDs...</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Lightbulb className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>RGB LED Setup</CardTitle>
            <CardDescription>Test and configure your lamp's LEDs</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 text-red-500 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        {/* LED Info */}
        <div className="p-3 rounded-lg bg-muted">
          <div className="text-sm">
            <span className="font-medium">LED Count:</span>{' '}
            <span className="text-muted-foreground">{rgbStatus?.led_count || 0} LEDs</span>
          </div>
        </div>

        {/* Brightness Control */}
        <div className="space-y-3">
          <Label className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4" />
            Brightness
          </Label>
          <div className="flex gap-3 items-center">
            <input
              type="range"
              min="0"
              max="100"
              value={brightness}
              onChange={handleBrightnessChange}
              className="flex-1 h-2 rounded-full bg-muted appearance-none cursor-pointer"
            />
            <span className="text-sm w-10 text-right">{brightness}%</span>
          </div>
        </div>

        {/* Test Button */}
        <div className="space-y-3">
          <Button
            variant="secondary"
            onClick={() => testMutation.mutate()}
            disabled={isTesting}
            className="w-full"
          >
            {isTesting ? (
              <>
                <div className="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full mr-2" />
                Testing LEDs...
              </>
            ) : testCompleted ? (
              <>
                <Check className="h-4 w-4 mr-2 text-green-500" />
                Test Again
              </>
            ) : (
              <>
                <Lightbulb className="h-4 w-4 mr-2" />
                Test LEDs
              </>
            )}
          </Button>
          {!testCompleted && (
            <p className="text-xs text-muted-foreground text-center">
              This will cycle through Red, Green, Blue, and White colors.
            </p>
          )}
          {testCompleted && (
            <p className="text-xs text-green-500 text-center flex items-center justify-center gap-1">
              <Check className="h-3 w-3" />
              LED test completed successfully
            </p>
          )}
        </div>

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => skipMutation.mutate()}
              disabled={skipMutation.isPending}
            >
              <SkipForward className="mr-2 h-4 w-4" />
              Skip
            </Button>
            <Button
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
            >
              Continue
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Voice type
type Voice = {
  id: string
  name: string
  description: string
  gender: string
  default?: boolean
}

// AI Backend Step (replaces Environment Step)
function EnvironmentStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [selectedBackend, setSelectedBackend] = useState<'livekit' | 'local'>('livekit')
  const [openaiKey, setOpenaiKey] = useState('')
  const [selectedVoice, setSelectedVoice] = useState<string>('')
  const [isValidatingKey, setIsValidatingKey] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keyValid, setKeyValid] = useState(false)
  const [isPlayingPreview, setIsPlayingPreview] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // LiveKit Cloud credentials
  const [livekitUrl, setLivekitUrl] = useState('')
  const [livekitApiKey, setLivekitApiKey] = useState('')
  const [livekitApiSecret, setLivekitApiSecret] = useState('')
  const [livekitConfigured, setLivekitConfigured] = useState(false)
  const [livekitError, setLivekitError] = useState<string | null>(null)
  const [isConfiguringLivekit, setIsConfiguringLivekit] = useState(false)

  // Fetch backend options
  const { data: backendOptions } = useQuery({
    queryKey: ['ai-backend-options'],
    queryFn: setupApi.getAIBackendOptions,
  })

  // Fetch LiveKit status
  const { data: livekitStatus, refetch: refetchLivekitStatus } = useQuery({
    queryKey: ['livekit-status'],
    queryFn: setupApi.getLiveKitStatus,
    enabled: selectedBackend === 'livekit',
  })

  // Fetch voices for selected backend
  const { data: voicesData } = useQuery({
    queryKey: ['voices', selectedBackend],
    queryFn: () => setupApi.getVoices(selectedBackend),
    enabled: !!selectedBackend,
  })

  // Fetch local config for Ollama status
  const { data: localConfig } = useQuery({
    queryKey: ['local-config'],
    queryFn: setupApi.getLocalConfig,
    enabled: selectedBackend === 'local',
  })

  // Set default voice when voices load
  useEffect(() => {
    if (voicesData?.voices && !selectedVoice) {
      const defaultVoice = voicesData.voices.find(v => v.default) || voicesData.voices[0]
      if (defaultVoice) {
        setSelectedVoice(defaultVoice.id)
      }
    }
  }, [voicesData, selectedVoice])

  // Reset voice when backend changes
  useEffect(() => {
    setSelectedVoice('')
    setKeyError(null)
    setKeyValid(false)
  }, [selectedBackend])

  // Check if OpenAI key is already configured
  useEffect(() => {
    if (backendOptions?.current === 'livekit') {
      const livekitBackend = backendOptions.backends.find(b => b.id === 'livekit')
      if (livekitBackend?.configured) {
        setKeyValid(true)
      }
    }
  }, [backendOptions])

  // Check if LiveKit Cloud is already configured
  useEffect(() => {
    if (livekitStatus?.configured) {
      setLivekitConfigured(true)
      if (livekitStatus.url) setLivekitUrl(livekitStatus.url)
      if (livekitStatus.api_key) setLivekitApiKey(livekitStatus.api_key)
    }
  }, [livekitStatus])

  const validateKeyMutation = useMutation({
    mutationFn: (key: string) => setupApi.validateOpenAIKey(key),
    onSuccess: (data) => {
      setIsValidatingKey(false)
      if (data.valid) {
        setKeyValid(true)
        setKeyError(null)
      } else {
        setKeyValid(false)
        setKeyError(data.error || 'Invalid API key')
      }
    },
    onError: () => {
      setIsValidatingKey(false)
      setKeyError('Failed to validate key')
    },
  })

  const configureMutation = useMutation({
    mutationFn: () => {
      const config: any = { backend: selectedBackend }

      if (selectedBackend === 'livekit') {
        if (openaiKey) config.openai_key = openaiKey
        config.openai_voice = selectedVoice || 'ballad'
      } else {
        config.piper_voice = selectedVoice || 'ryan-medium.onnx'
      }

      return setupApi.configureAIBackend(config)
    },
    onSuccess: (data) => {
      if (data.success) {
        onNext()
      } else {
        setKeyError(data.error || 'Configuration failed')
      }
    },
  })

  const handleValidateKey = () => {
    if (openaiKey) {
      setIsValidatingKey(true)
      setKeyError(null)
      validateKeyMutation.mutate(openaiKey)
    }
  }

  const handleConfigureLivekit = async () => {
    if (!livekitUrl || !livekitApiKey || !livekitApiSecret) {
      setLivekitError('All LiveKit fields are required')
      return
    }

    setIsConfiguringLivekit(true)
    setLivekitError(null)

    try {
      const result = await setupApi.configureLiveKit({
        url: livekitUrl,
        api_key: livekitApiKey,
        api_secret: livekitApiSecret,
      })

      if (result.success) {
        setLivekitConfigured(true)
        refetchLivekitStatus()
      } else {
        setLivekitError(result.error || 'Configuration failed')
      }
    } catch (e) {
      setLivekitError('Failed to configure LiveKit')
    } finally {
      setIsConfiguringLivekit(false)
    }
  }

  const handlePlayPreview = async (voiceId: string) => {
    if (selectedBackend === 'local') {
      // Stop current preview if playing
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }

      setIsPlayingPreview(true)

      try {
        // For local backend, fetch audio from API
        const url = `/api/v1/setup/ai-backend/test-voice`
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            backend: 'local',
            voice_id: voiceId,
            text: 'Hello! I am your LeLamp, ready to assist you.',
          }),
        })

        if (response.ok && response.headers.get('content-type')?.includes('audio')) {
          const blob = await response.blob()
          const audioUrl = URL.createObjectURL(blob)
          const audio = new Audio(audioUrl)
          audioRef.current = audio

          audio.onended = () => {
            setIsPlayingPreview(false)
            URL.revokeObjectURL(audioUrl)
          }

          audio.onerror = () => {
            setIsPlayingPreview(false)
            URL.revokeObjectURL(audioUrl)
          }

          await audio.play()
        } else {
          setIsPlayingPreview(false)
        }
      } catch (error) {
        console.error('Preview error:', error)
        setIsPlayingPreview(false)
      }
    }
  }

  const openaiConfigured = keyValid || backendOptions?.backends.find(b => b.id === 'livekit')?.configured
  const canProceed =
    selectedBackend === 'local' ||
    (selectedBackend === 'livekit' && openaiConfigured && livekitConfigured)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Cog className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>AI Backend</CardTitle>
            <CardDescription>Choose how LeLamp thinks and speaks</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Backend Selection */}
        <div className="space-y-3">
          <Label>Select AI Backend</Label>
          <div className="grid grid-cols-1 gap-3">
            {/* LiveKit + OpenAI */}
            <button
              type="button"
              onClick={() => setSelectedBackend('livekit')}
              className={`p-4 text-left rounded-lg border-2 transition-all ${
                selectedBackend === 'livekit'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium flex items-center gap-2">
                    LiveKit + OpenAI
                    <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-500">Recommended</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Real-time voice with GPT-4o. Low latency, natural conversations.
                  </p>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded bg-muted">Cloud-based</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-muted">Multiple voices</span>
                  </div>
                </div>
                {selectedBackend === 'livekit' && (
                  <Check className="h-5 w-5 text-primary shrink-0" />
                )}
              </div>
            </button>

            {/* Local AI */}
            <button
              type="button"
              onClick={() => setSelectedBackend('local')}
              className={`p-4 text-left rounded-lg border-2 transition-all ${
                selectedBackend === 'local'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium">Local AI</div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Whisper + Ollama + Piper. Runs entirely on device, no API costs.
                  </p>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded bg-muted">Offline capable</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-muted">Privacy focused</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-muted">No API costs</span>
                  </div>
                </div>
                {selectedBackend === 'local' && (
                  <Check className="h-5 w-5 text-primary shrink-0" />
                )}
              </div>
            </button>
          </div>
        </div>

        {/* LiveKit Configuration */}
        {selectedBackend === 'livekit' && (
          <div className="space-y-4 pt-2 border-t">
            <div className="space-y-2">
              <Label htmlFor="openai-key">OpenAI API Key</Label>
              <div className="flex gap-2">
                <Input
                  id="openai-key"
                  type="password"
                  placeholder="sk-..."
                  value={openaiKey}
                  onChange={(e) => {
                    setOpenaiKey(e.target.value)
                    setKeyValid(false)
                    setKeyError(null)
                  }}
                  disabled={keyValid}
                />
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleValidateKey}
                  disabled={!openaiKey || isValidatingKey || keyValid}
                >
                  {isValidatingKey ? '...' : keyValid ? 'Valid' : 'Verify'}
                </Button>
              </div>
              {keyError && (
                <p className="text-sm text-red-500 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {keyError}
                </p>
              )}
              {keyValid && (
                <p className="text-sm text-green-500 flex items-center gap-1">
                  <Check className="h-3 w-3" />
                  API key verified
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Get your API key from{' '}
                <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  platform.openai.com
                </a>
              </p>
            </div>

            {/* LiveKit Cloud Configuration */}
            <div className="space-y-3 pt-4 border-t">
              <div className="flex items-center justify-between">
                <Label className="text-base font-medium">LiveKit Cloud</Label>
                {livekitConfigured && (
                  <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-500 flex items-center gap-1">
                    <Check className="h-3 w-3" /> Configured
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                LiveKit Cloud handles real-time audio streaming.
                <a href="https://cloud.livekit.io" target="_blank" rel="noreferrer" className="text-primary hover:underline ml-1">
                  Sign up for free
                </a>
              </p>

              {!livekitConfigured ? (
                <div className="space-y-3 p-4 rounded-lg border bg-muted/30">
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
                      placeholder="Enter your API secret"
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
                    type="button"
                    onClick={handleConfigureLivekit}
                    disabled={isConfiguringLivekit || !livekitUrl || !livekitApiKey || !livekitApiSecret}
                    className="w-full"
                  >
                    {isConfiguringLivekit ? 'Configuring...' : 'Configure LiveKit'}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Find these in your LiveKit Cloud project settings under "API Keys"
                  </p>
                </div>
              ) : (
                <div className="p-3 rounded-lg border bg-green-500/5 border-green-500/20">
                  <div className="flex items-center gap-2 text-sm">
                    <Check className="h-4 w-4 text-green-500" />
                    <span>Connected to LiveKit Cloud</span>
                  </div>
                  {livekitStatus?.room_name && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Room: <code className="bg-muted px-1 rounded">{livekitStatus.room_name}</code>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* OpenAI Voice Selection */}
            {voicesData?.voices && (
              <div className="space-y-2">
                <Label>Voice</Label>
                <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                  {voicesData.voices.map((voice: Voice) => (
                    <button
                      key={voice.id}
                      type="button"
                      onClick={() => setSelectedVoice(voice.id)}
                      className={`p-3 text-left rounded-lg border transition-colors ${
                        selectedVoice === voice.id
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="font-medium text-sm">{voice.name}</div>
                      <div className="text-xs text-muted-foreground">{voice.description}</div>
                      <div className="text-xs text-muted-foreground capitalize mt-1">{voice.gender}</div>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Voice preview available after setup. OpenAI voices are high quality neural TTS.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Local Configuration */}
        {selectedBackend === 'local' && (
          <div className="space-y-4 pt-2 border-t">
            {/* Ollama Status */}
            {localConfig && (
              <div className="flex items-center gap-2 text-sm">
                <span className={`h-2 w-2 rounded-full ${localConfig.ollama.available ? 'bg-green-500' : 'bg-yellow-500'}`} />
                <span>
                  Ollama: {localConfig.ollama.available
                    ? `Connected (${localConfig.ollama.current_model})`
                    : 'Not detected - will use default model'}
                </span>
              </div>
            )}

            {/* Piper Voice Selection */}
            {voicesData?.voices && voicesData.voices.length > 0 ? (
              <div className="space-y-2">
                <Label>Voice</Label>
                <div className="grid grid-cols-1 gap-2 max-h-64 overflow-y-auto">
                  {voicesData.voices.map((voice: Voice) => (
                    <div
                      key={voice.id}
                      className={`p-3 rounded-lg border transition-colors flex items-center justify-between ${
                        selectedVoice === voice.id
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedVoice(voice.id)}
                        className="flex-1 text-left"
                      >
                        <div className="font-medium text-sm">{voice.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {voice.description} · {voice.gender}
                        </div>
                      </button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handlePlayPreview(voice.id)}
                        disabled={isPlayingPreview}
                        className="ml-2"
                      >
                        {isPlayingPreview ? '...' : '▶ Test'}
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-sm text-yellow-500 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Piper voices not found. Install voices to use local TTS.
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button
            onClick={() => configureMutation.mutate()}
            disabled={!canProceed || configureMutation.isPending}
          >
            {configureMutation.isPending ? 'Saving...' : 'Continue'}
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// Location search result type
type LocationResult = {
  city: string
  region: string
  country: string
  lat: number
  lon: number
  display_name: string
}

// Location Step
function LocationStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<LocationResult[]>([])
  const [selectedLocation, setSelectedLocation] = useState<LocationResult | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const searchMutation = useMutation({
    mutationFn: async (query: string) => {
      const response = await fetch(`/api/v1/setup/location/search?q=${encodeURIComponent(query)}`)
      return response.json()
    },
    onSuccess: (data) => {
      if (data.success) {
        setSearchResults(data.results)
        setSearchError(null)
      } else {
        setSearchError(data.error || 'Search failed')
        setSearchResults([])
      }
      setIsSearching(false)
    },
    onError: () => {
      setSearchError('Search failed')
      setIsSearching(false)
    }
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selectedLocation) throw new Error('No location selected')
      return setupApi.saveLocation({
        city: selectedLocation.city,
        region: selectedLocation.region,
        country: selectedLocation.country,
        lat: selectedLocation.lat,
        lon: selectedLocation.lon,
      })
    },
    onSuccess: () => onNext(),
  })

  const handleSearch = () => {
    if (searchQuery.length >= 2) {
      setIsSearching(true)
      searchMutation.mutate(searchQuery)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <MapPin className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Location</CardTitle>
            <CardDescription>Help LeLamp know your timezone for alarms and weather</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="city">Search for your city</Label>
          <div className="flex gap-2">
            <Input
              id="city"
              placeholder="San Francisco"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <Button
              type="button"
              variant="secondary"
              onClick={handleSearch}
              disabled={isSearching || searchQuery.length < 2}
            >
              {isSearching ? '...' : 'Search'}
            </Button>
          </div>
        </div>

        {searchError && (
          <p className="text-sm text-red-500">{searchError}</p>
        )}

        {searchResults.length > 0 && (
          <div className="space-y-2">
            <Label>Select your location</Label>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {searchResults.map((result, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setSelectedLocation(result)}
                  className={`w-full p-2 text-left rounded-lg border transition-colors text-sm ${
                    selectedLocation === result
                      ? 'border-primary bg-primary/10'
                      : 'border-border hover:border-primary/50'
                  }`}
                >
                  <div className="font-medium">{result.city}</div>
                  <div className="text-xs text-muted-foreground">
                    {[result.region, result.country].filter(Boolean).join(', ')}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedLocation && (
          <div className="p-3 rounded-lg bg-green-500/10 text-green-600 text-sm">
            <div className="font-medium">Selected: {selectedLocation.city}</div>
            <div className="text-xs">
              {[selectedLocation.region, selectedLocation.country].filter(Boolean).join(', ')}
              {' • '}
              {selectedLocation.lat.toFixed(4)}, {selectedLocation.lon.toFixed(4)}
            </div>
          </div>
        )}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={() => selectedLocation ? saveMutation.mutate() : onNext()}>
            {selectedLocation ? 'Continue' : 'Skip'}
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// Personality Step
function PersonalityStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [name, setName] = useState('LeLamp')
  const [selectedCharacter, setSelectedCharacter] = useState('LeLamp')
  const [defaultColor, setDefaultColor] = useState('#000096')

  // Fetch available characters
  const { data: personalityData } = useQuery({
    queryKey: ['personality'],
    queryFn: setupApi.getPersonality,
  })

  // Set initial values from API
  useEffect(() => {
    if (personalityData?.success) {
      if (personalityData.name) setName(personalityData.name)
      if (personalityData.character_id) setSelectedCharacter(personalityData.character_id)
      if (personalityData.default_color) setDefaultColor(rgbToHex(personalityData.default_color))
    }
  }, [personalityData])

  const characters = personalityData?.characters || []
  const currentCharacter = characters.find(c => c.id === selectedCharacter)

  const saveMutation = useMutation({
    mutationFn: () => setupApi.savePersonality({
      name,
      character_id: selectedCharacter,
      default_color: hexToRgb(defaultColor),
    }),
    onSuccess: () => onNext(),
  })

  // Preset colors for quick selection
  const presetColors = [
    '#ef4444', // Red
    '#f97316', // Orange
    '#eab308', // Yellow
    '#22c55e', // Green
    '#06b6d4', // Cyan
    '#3b82f6', // Blue
    '#8b5cf6', // Violet
    '#ec4899', // Pink
    '#ffffff', // White
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <User className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Personality</CardTitle>
            <CardDescription>Give your lamp a name, character, and favorite color</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Name Input */}
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            placeholder="LeLamp"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* Character Selection */}
        <div className="space-y-2">
          <Label>Character</Label>
          <div className="grid gap-3">
            {characters.map((char) => (
              <button
                key={char.id}
                onClick={() => setSelectedCharacter(char.id)}
                className={`p-4 rounded-lg border text-left transition-all ${
                  selectedCharacter === char.id
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="font-semibold text-lg">{char.name}</div>
                <div className="text-sm text-muted-foreground mt-1 line-clamp-2">
                  {char.description}
                </div>
              </button>
            ))}
          </div>

          {/* Show selected character details */}
          {currentCharacter && (
            <div className="mt-3 p-3 rounded-lg bg-muted/50 text-sm">
              <div className="font-medium mb-1">Speech Style:</div>
              <div className="text-muted-foreground line-clamp-3">
                {currentCharacter.speech_style}
              </div>
            </div>
          )}
        </div>

        {/* Default Color */}
        <div className="space-y-3">
          <Label>Default LED Color</Label>
          <div className="flex items-center gap-4">
            {/* Color picker input */}
            <div className="relative">
              <input
                type="color"
                value={defaultColor}
                onChange={(e) => setDefaultColor(e.target.value)}
                className="w-16 h-16 rounded-lg cursor-pointer border-2 border-border"
                style={{ padding: 0 }}
              />
            </div>

            {/* Preset colors */}
            <div className="flex flex-wrap gap-2">
              {presetColors.map((color) => (
                <button
                  key={color}
                  onClick={() => setDefaultColor(color)}
                  className={`w-8 h-8 rounded-full border-2 transition-all ${
                    defaultColor.toLowerCase() === color.toLowerCase()
                      ? 'border-primary ring-2 ring-primary/30 scale-110'
                      : 'border-border hover:scale-105'
                  }`}
                  style={{ backgroundColor: color }}
                  title={color}
                />
              ))}
            </div>
          </div>
          <div className="text-xs text-muted-foreground">
            Selected: <span className="font-mono">{defaultColor}</span>
          </div>
        </div>

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving...' : 'Finish Setup'}
            <Check className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// Motor Calibration Step
function MotorCalibrationStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const queryClient = useQueryClient()
  const [calibrationPhase, setCalibrationPhase] = useState<
    'start' | 'connecting' | 'homing' | 'range' | 'finalizing' | 'done' | 'error' | 'skipped'
  >('start')
  const [error, setError] = useState<string | null>(null)
  const [positions, setPositions] = useState<Record<string, number>>({})
  const [rangeMins, setRangeMins] = useState<Record<string, number>>({})
  const [rangeMaxs, setRangeMaxs] = useState<Record<string, number>>({})

  // Skip mutation - disables motors
  const skipMutation = useMutation({
    mutationFn: () => setupApi.skipStep('motor-calibration', 'motors'),
    onSuccess: () => {
      setCalibrationPhase('skipped')
      queryClient.invalidateQueries({ queryKey: ['dashboard-status'] })
      setTimeout(() => onNext(), 1500)
    },
    onError: (err) => {
      setError(String(err))
    },
  })

  // Poll for positions during calibration
  const { data: positionsData } = useQuery({
    queryKey: ['calibration-positions'],
    queryFn: calibrationApi.getPositions,
    refetchInterval: calibrationPhase === 'homing' || calibrationPhase === 'range' ? 200 : false,
    enabled: calibrationPhase === 'homing' || calibrationPhase === 'range',
  })


  useEffect(() => {
    if (positionsData?.success) {
      setPositions(positionsData.positions)
      // Also get range data from positions endpoint (more frequent updates)
      if (positionsData.range_mins) {
        setRangeMins(positionsData.range_mins)
      }
      if (positionsData.range_maxs) {
        setRangeMaxs(positionsData.range_maxs)
      }
    }
  }, [positionsData])

  const startMutation = useMutation({
    mutationFn: calibrationApi.start,
    onSuccess: (data) => {
      if (data.success) {
        setCalibrationPhase('homing')
      } else {
        setError(data.error || 'Failed to connect to motors')
        setCalibrationPhase('error')
      }
    },
    onError: (err) => {
      setError(String(err))
      setCalibrationPhase('error')
    },
  })

  const startRangeMutation = useMutation({
    mutationFn: calibrationApi.startRange,
  })

  const recordHomingMutation = useMutation({
    mutationFn: calibrationApi.recordHoming,
    onSuccess: (data) => {
      if (data.success) {
        // Start range recording mode, then switch to range phase
        startRangeMutation.mutate(undefined, {
          onSuccess: () => setCalibrationPhase('range'),
        })
      } else {
        setError(data.error || 'Failed to record homing position')
      }
    },
  })

  const recordRangesMutation = useMutation({
    mutationFn: calibrationApi.recordRanges,
    onSuccess: (data) => {
      if (data.success) {
        setCalibrationPhase('finalizing')
        finalizeMutation.mutate()
      } else {
        setError(data.error || 'Failed to record ranges')
      }
    },
  })

  const finalizeMutation = useMutation({
    mutationFn: calibrationApi.finalize,
    onSuccess: (data) => {
      if (data.success) {
        setCalibrationPhase('done')
        queryClient.invalidateQueries({ queryKey: ['dashboard-status'] })
        // Auto advance after short delay
        setTimeout(() => onNext(), 1500)
      } else {
        setError(data.error || 'Failed to save calibration')
        setCalibrationPhase('error')
      }
    },
  })

  const cancelMutation = useMutation({
    mutationFn: calibrationApi.cancel,
    onSuccess: () => {
      setCalibrationPhase('start')
      setError(null)
    },
  })

  const handleStartCalibration = () => {
    setCalibrationPhase('connecting')
    setError(null)
    startMutation.mutate()
  }

  const motorNames: Record<string, string> = {
    base_yaw: 'Base Yaw',
    base_pitch: 'Base Pitch',
    elbow_pitch: 'Elbow',
    wrist_roll: 'Wrist Roll',
    wrist_pitch: 'Wrist Pitch',
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Cog className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Motor Calibration</CardTitle>
            <CardDescription>Calibrate your lamp's motors for accurate movement</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 text-red-500 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {calibrationPhase === 'start' && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              This wizard will guide you through calibrating the lamp's motors.
              You'll need to physically move the lamp to set its home position and range of motion.
            </p>
            <div className="p-3 rounded-lg bg-yellow-500/10 text-yellow-600">
              <p className="text-sm font-medium">Before starting:</p>
              <ul className="text-sm mt-1 list-disc list-inside">
                <li>Make sure the lamp is powered on</li>
                <li>Ensure the motors are connected via USB</li>
                <li>Clear the area around the lamp</li>
              </ul>
            </div>
          </div>
        )}

        {calibrationPhase === 'connecting' && (
          <div className="text-center py-4">
            <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Parking lamp safely...</p>
            <p className="text-xs text-muted-foreground mt-1">Playing sleep animation</p>
          </div>
        )}

        {calibrationPhase === 'homing' && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Move the lamp to its <strong>home position</strong> (centered, neutral pose).
              The motors are now in compliant mode - you can move them by hand.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(positions).map(([motor, pos]) => (
                <div key={motor} className="p-2 rounded bg-muted text-sm">
                  <span className="font-medium">{motorNames[motor] || motor}:</span>{' '}
                  <span className="text-muted-foreground">{Math.round(pos)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {calibrationPhase === 'range' && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Now move <strong>each motor</strong> through its full range of motion.
              Push each joint to its minimum and maximum positions.
            </p>
            <div className="space-y-2">
              {Object.entries(positions).map(([motor, pos]) => {
                const min = rangeMins[motor]
                const max = rangeMaxs[motor]
                const hasRange = min !== undefined && max !== undefined
                return (
                  <div key={motor} className="p-2 rounded bg-muted text-sm">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">{motorNames[motor] || motor}</span>
                      <span className="text-muted-foreground">Current: {Math.round(pos)}</span>
                    </div>
                    {hasRange && (
                      <div className="flex justify-between text-xs text-muted-foreground mt-1">
                        <span className="text-blue-500">Min: {Math.round(min)}</span>
                        <span className="text-green-500">Max: {Math.round(max)}</span>
                        <span>Range: {Math.round(max - min)}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {calibrationPhase === 'finalizing' && (
          <div className="text-center py-4">
            <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Saving calibration...</p>
          </div>
        )}

        {calibrationPhase === 'done' && (
          <div className="text-center py-4">
            <div className="h-12 w-12 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-2">
              <Check className="h-6 w-6 text-green-500" />
            </div>
            <p className="text-sm font-medium">Calibration complete!</p>
          </div>
        )}

        {calibrationPhase === 'skipped' && (
          <div className="text-center py-4">
            <div className="h-12 w-12 rounded-full bg-yellow-500/10 flex items-center justify-center mx-auto mb-2">
              <SkipForward className="h-6 w-6 text-yellow-500" />
            </div>
            <p className="text-sm font-medium">Motor calibration skipped</p>
            <p className="text-xs text-muted-foreground mt-1">
              Motors have been disabled. You can enable them later in Settings.
            </p>
          </div>
        )}

        {calibrationPhase === 'error' && (
          <div className="text-center py-4">
            <p className="text-sm text-muted-foreground">
              Calibration failed. Please check the motor connection and try again.
            </p>
          </div>
        )}

        <div className="flex justify-between pt-4">
          <Button
            variant="outline"
            onClick={() => {
              if (calibrationPhase !== 'start' && calibrationPhase !== 'done' && calibrationPhase !== 'skipped') {
                cancelMutation.mutate()
              } else {
                onBack()
              }
            }}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            {calibrationPhase === 'start' || calibrationPhase === 'done' || calibrationPhase === 'skipped' ? 'Back' : 'Cancel'}
          </Button>

          {calibrationPhase === 'start' && (
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={() => skipMutation.mutate()}
                disabled={skipMutation.isPending}
              >
                <SkipForward className="mr-2 h-4 w-4" />
                Skip (No Motors)
              </Button>
              <Button onClick={handleStartCalibration}>
                Start Calibration
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          )}

          {calibrationPhase === 'homing' && (
            <Button
              onClick={() => recordHomingMutation.mutate()}
              disabled={recordHomingMutation.isPending}
            >
              Record Home Position
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          )}

          {calibrationPhase === 'range' && (
            <Button
              onClick={() => recordRangesMutation.mutate()}
              disabled={recordRangesMutation.isPending}
            >
              Finish Calibration
              <Check className="ml-2 h-4 w-4" />
            </Button>
          )}

          {calibrationPhase === 'error' && (
            <Button onClick={handleStartCalibration}>
              Try Again
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Complete Step
function CompleteStep({ isCalibrationOnly = false }: { isCalibrationOnly?: boolean }) {
  const navigate = useNavigate()

  const finishMutation = useMutation({
    mutationFn: setupApi.finish,
    onSuccess: () => navigate('/dashboard'),
  })

  useEffect(() => {
    if (isCalibrationOnly) {
      // Just redirect to dashboard for calibration-only mode
      navigate('/dashboard')
    } else {
      finishMutation.mutate()
    }
  }, [isCalibrationOnly])

  return (
    <Card>
      <CardHeader className="text-center">
        <div className="mx-auto mb-4 h-20 w-20 rounded-full bg-green-500/10 flex items-center justify-center">
          <Check className="h-10 w-10 text-green-500" />
        </div>
        <CardTitle className="text-2xl">
          {isCalibrationOnly ? 'Calibration Complete!' : 'Setup Complete!'}
        </CardTitle>
        <CardDescription>
          Your LeLamp is ready to go. Taking you to the dashboard...
        </CardDescription>
      </CardHeader>
    </Card>
  )
}
