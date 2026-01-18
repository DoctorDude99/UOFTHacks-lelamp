import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { setupApi, agentApi } from '@/lib/api'

// Voice type
type Voice = {
  id: string
  name: string
  description: string
  gender: string
  default?: boolean
}

// Provider type
type Provider = {
  id: string
  name: string
  description: string
  api_key_env: string
  api_key_url: string
  recommended: boolean
  coming_soon: boolean
  configured: boolean
}

interface AIBackendSettingsProps {
  // Compact mode for settings page (no large cards, just selects)
  compact?: boolean
  // Callback when configuration is saved
  onSaved?: () => void
}

export function AIBackendSettings({ compact = false, onSaved }: AIBackendSettingsProps) {
  const queryClient = useQueryClient()
  const [selectedBackend, setSelectedBackend] = useState<'livekit-realtime' | 'local'>('livekit-realtime')
  const [selectedProvider, setSelectedProvider] = useState<string>('openai')
  const [apiKey, setApiKey] = useState('')
  const [selectedVoice, setSelectedVoice] = useState<string>('')
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keyValid, setKeyValid] = useState(false)
  const [isPlayingPreview, setIsPlayingPreview] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [restartRequired, setRestartRequired] = useState(false)
  const [isRestarting, setIsRestarting] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Server VAD settings (for cloud turn detection)
  const [serverVadThreshold, setServerVadThreshold] = useState(0.75)
  const [serverSilenceDuration, setServerSilenceDuration] = useState(600)

  // Handle service restart
  const handleRestart = async () => {
    setIsRestarting(true)
    try {
      await agentApi.restartService()
      // Service is restarting, clear the notification after a delay
      setTimeout(() => {
        setRestartRequired(false)
        setIsRestarting(false)
      }, 3000)
    } catch (e) {
      console.error('Service restart failed:', e)
      setIsRestarting(false)
    }
  }

  // Fetch backend options
  const { data: backendOptions, isLoading: loadingOptions } = useQuery({
    queryKey: ['ai-backend-options'],
    queryFn: setupApi.getAIBackendOptions,
  })

  // Fetch current backend config
  const { data: currentConfig, isLoading: loadingCurrent } = useQuery({
    queryKey: ['ai-backend-current'],
    queryFn: setupApi.getAIBackendCurrent,
  })

  // Fetch voices for selected backend and provider
  const { data: voicesData, isLoading: loadingVoices } = useQuery({
    queryKey: ['voices', selectedBackend, selectedProvider],
    queryFn: () => setupApi.getVoices(selectedBackend, selectedProvider),
    enabled: !!selectedBackend,
  })

  // Fetch local config for Ollama status
  const { data: localConfig } = useQuery({
    queryKey: ['local-config'],
    queryFn: setupApi.getLocalConfig,
    enabled: selectedBackend === 'local',
  })

  // Debounced auto-save function
  const debouncedSave = useCallback(
    (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      return (config: { backend: string; provider?: string; api_key?: string; voice?: string; piper_voice?: string }) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(async () => {
          setIsSaving(true)
          try {
            const result = await setupApi.configureAIBackend(config)
            if (result.success) {
              queryClient.invalidateQueries({ queryKey: ['ai-backend-current'] })
              queryClient.invalidateQueries({ queryKey: ['ai-backend-options'] })
              // Show restart notification when backend type changes
              if (result.restart_required) {
                setRestartRequired(true)
              }
              onSaved?.()
            } else {
              setKeyError(result.error || 'Save failed')
            }
          } catch (e) {
            console.error('AI config save failed:', e)
          } finally {
            setIsSaving(false)
          }
        }, 500)
      }
    })(),
    [queryClient, onSaved]
  )

  // Fetch full settings for microphone config
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await fetch('/api/v1/dashboard/settings')
      return res.json()
    },
  })

  // Initialize from current config
  useEffect(() => {
    if (currentConfig?.success) {
      // Normalize backend name (support legacy "livekit")
      let backend = currentConfig.backend || 'livekit-realtime'
      if (backend === 'livekit') backend = 'livekit-realtime'
      setSelectedBackend(backend as 'livekit-realtime' | 'local')

      // Set provider
      if (currentConfig.provider) {
        setSelectedProvider(currentConfig.provider)
      }

      if (currentConfig.voice) {
        setSelectedVoice(currentConfig.voice)
      }

      // Key is valid if configured and no missing keys
      if (currentConfig.configured && (!currentConfig.missing_keys || currentConfig.missing_keys.length === 0)) {
        setKeyValid(true)
      }
    }
  }, [currentConfig])

  // Sync server VAD settings from config
  useEffect(() => {
    const micConfig = settingsData?.config?.microphone || {}
    if (micConfig.server_vad_threshold !== undefined) {
      setServerVadThreshold(micConfig.server_vad_threshold)
    }
    if (micConfig.server_silence_duration_ms !== undefined) {
      setServerSilenceDuration(micConfig.server_silence_duration_ms)
    }
  }, [settingsData])

  // Set default voice when voices load
  useEffect(() => {
    if (voicesData?.voices && !selectedVoice) {
      const defaultVoice = voicesData.voices.find((v: Voice) => v.default) || voicesData.voices[0]
      if (defaultVoice) {
        setSelectedVoice(defaultVoice.id)
      }
    }
  }, [voicesData, selectedVoice])

  // Reset voice when backend or provider changes
  useEffect(() => {
    setSelectedVoice('')
    setKeyError(null)
    // Check if current provider is configured
    if (selectedBackend === 'livekit-realtime') {
      const provider = backendOptions?.providers?.find((p: Provider) => p.id === selectedProvider)
      setKeyValid(provider?.configured || false)
    } else {
      setKeyValid(false)
    }
  }, [selectedBackend, selectedProvider, backendOptions])

  // Auto-save when backend changes
  const handleBackendChange = (backend: 'livekit-realtime' | 'local') => {
    setSelectedBackend(backend)
    const config: any = { backend }
    if (backend === 'livekit-realtime') {
      config.provider = selectedProvider
      if (apiKey) config.api_key = apiKey
      config.voice = selectedVoice || 'ballad'
    } else {
      config.piper_voice = selectedVoice || 'ryan-medium.onnx'
    }
    debouncedSave(config)
  }

  // Auto-save when provider changes
  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider)
    setSelectedVoice('') // Reset voice for new provider
    setApiKey('') // Clear API key input
    setKeyError(null)
    // Check if this provider is configured
    const providerInfo = backendOptions?.providers?.find((p: Provider) => p.id === provider)
    setKeyValid(providerInfo?.configured || false)
    // Save provider change
    debouncedSave({
      backend: 'livekit-realtime',
      provider,
    })
  }

  // Auto-save when voice changes
  const handleVoiceChange = (voiceId: string) => {
    setSelectedVoice(voiceId)
    const config: any = { backend: selectedBackend }
    if (selectedBackend === 'livekit-realtime') {
      config.provider = selectedProvider
      if (apiKey) config.api_key = apiKey
      config.voice = voiceId
    } else {
      config.piper_voice = voiceId
    }
    debouncedSave(config)
  }

  // Auto-save when API key changes
  const handleKeyChange = (key: string) => {
    setApiKey(key)
    setKeyError(null)
    // Basic validation - just check if it looks like an API key
    if (key && key.length >= 10) {
      setKeyValid(true)
      debouncedSave({
        backend: 'livekit-realtime',
        provider: selectedProvider,
        api_key: key,
        voice: selectedVoice || 'ballad',
      })
    } else if (key) {
      setKeyValid(false)
      setKeyError('API key seems too short')
    }
  }

  // Debounced save for server VAD settings
  const debouncedVadSave = useCallback(
    (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      return async (updates: {
        server_vad_threshold?: number
        server_silence_duration_ms?: number
      }) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(async () => {
          try {
            await fetch('/api/v1/dashboard/settings/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ microphone: updates }),
            })
            setRestartRequired(true) // VAD changes require restart
          } catch (e) {
            console.error('VAD settings save failed:', e)
          }
        }, 300)
      }
    })(),
    []
  )

  const handleServerVadChange = (value: number) => {
    setServerVadThreshold(value)
    debouncedVadSave({ server_vad_threshold: value })
  }

  const handleSilenceDurationChange = (value: number) => {
    setServerSilenceDuration(value)
    debouncedVadSave({ server_silence_duration_ms: value })
  }

  // Get current provider info
  const currentProviderInfo = backendOptions?.providers?.find((p: Provider) => p.id === selectedProvider)

  const handlePlayPreview = async (voiceId: string, backend: 'local' | 'livekit-realtime' | 'livekit' = selectedBackend) => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }

    setIsPlayingPreview(true)

    try {
      const url = `/api/v1/setup/ai-backend/test-voice`
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          backend,
          voice_id: voiceId,
          text: 'Hello! I am your LeLamp, ready to assist you.',
        }),
      })

      const data = await response.json()

      if (data.success) {
        // Audio plays on device, just show feedback briefly
        setTimeout(() => setIsPlayingPreview(false), 3000)
      } else {
        console.error('Preview error:', data.error)
        setKeyError(data.error || 'Failed to play preview')
        setIsPlayingPreview(false)
      }
    } catch (error) {
      console.error('Preview error:', error)
      setIsPlayingPreview(false)
    }
  }

  const isLoading = loadingOptions || loadingCurrent

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Compact mode - simpler layout for settings page
  if (compact) {
    return (
      <div className="space-y-4">
        {/* Restart Required Notification */}
        {restartRequired && (
          <div className="flex items-center justify-between gap-2 p-3 rounded-md bg-amber-500/10 border border-amber-500/30 text-sm">
            <div className="flex items-center gap-2">
              <RefreshCw className={`h-4 w-4 text-amber-500 shrink-0 ${isRestarting ? 'animate-spin' : ''}`} />
              <span className="text-amber-500">
                {isRestarting ? 'Restarting service...' : 'Restart required for changes to take effect'}
              </span>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleRestart}
              disabled={isRestarting}
              className="border-amber-500/50 text-amber-500 hover:bg-amber-500/10"
            >
              {isRestarting ? 'Restarting...' : 'Restart'}
            </Button>
          </div>
        )}

        {/* Backend Selection */}
        <div className="space-y-2">
          <Label htmlFor="ai-backend">AI Backend</Label>
          <select
            id="ai-backend"
            value={selectedBackend}
            onChange={(e) => handleBackendChange(e.target.value as 'livekit-realtime' | 'local')}
            className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
          >
            <option value="livekit-realtime">LiveKit Realtime</option>
            <option value="local">Local AI (Ollama + Piper)</option>
          </select>
        </div>

        {/* Provider Selection for LiveKit Realtime */}
        {selectedBackend === 'livekit-realtime' && backendOptions?.providers && (
          <div className="space-y-2">
            <Label htmlFor="ai-provider">AI Provider</Label>
            <select
              id="ai-provider"
              value={selectedProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
            >
              {backendOptions.providers
                .filter((p: Provider) => !p.coming_soon)
                .map((provider: Provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name} {provider.recommended ? '(Recommended)' : ''}
                  </option>
                ))}
            </select>
          </div>
        )}

        {/* API Key for LiveKit Realtime */}
        {selectedBackend === 'livekit-realtime' && (
          <div className="space-y-2">
            <Label htmlFor="api-key">{currentProviderInfo?.name || 'Provider'} API Key</Label>
            <div className="flex gap-2 items-center">
              <Input
                id="api-key"
                type="password"
                placeholder={keyValid && !apiKey ? '••••••••••••••••' : 'Enter API key...'}
                value={apiKey}
                onChange={(e) => handleKeyChange(e.target.value)}
              />
              {isSaving && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              {keyValid && !isSaving && <Check className="h-4 w-4 text-green-500" />}
            </div>
            {keyError && (
              <p className="text-xs text-red-500 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                {keyError}
              </p>
            )}
            {keyValid && !apiKey && (
              <p className="text-xs text-green-500 flex items-center gap-1">
                <Check className="h-3 w-3" />
                API key configured
              </p>
            )}
            {currentProviderInfo?.api_key_url && (
              <p className="text-xs text-muted-foreground">
                Get API key from{' '}
                <a href={currentProviderInfo.api_key_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  {new URL(currentProviderInfo.api_key_url).hostname}
                </a>
              </p>
            )}
          </div>
        )}

        {/* Local AI Status */}
        {selectedBackend === 'local' && localConfig && (
          <div className="flex items-center gap-2 text-sm p-2 rounded bg-muted">
            <span className={`h-2 w-2 rounded-full ${localConfig.ollama?.available ? 'bg-green-500' : 'bg-yellow-500'}`} />
            <span>
              Ollama: {localConfig.ollama?.available
                ? `Connected (${localConfig.ollama.current_model})`
                : 'Not detected'}
            </span>
          </div>
        )}

        {/* Voice Selection */}
        <div className="space-y-2">
          <Label htmlFor="voice">Voice</Label>
          {loadingVoices ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading voices...
            </div>
          ) : (
            <select
              id="voice"
              value={selectedVoice}
              onChange={(e) => handleVoiceChange(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm"
            >
              {voicesData?.voices?.map((voice: Voice) => (
                <option key={voice.id} value={voice.id}>
                  {voice.name} - {voice.description}
                </option>
              ))}
            </select>
          )}
          {selectedVoice && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handlePlayPreview(selectedVoice)}
              disabled={isPlayingPreview || (selectedBackend === 'livekit-realtime' && !keyValid)}
              className="mt-1"
            >
              {isPlayingPreview ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Playing...
                </>
              ) : (
                'Test Voice'
              )}
            </Button>
          )}
        </div>

        {/* Cloud VAD Settings (only for LiveKit Realtime) */}
        {selectedBackend === 'livekit-realtime' && (
          <div className="space-y-3 pt-3 border-t">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="server-vad" className="text-sm">Realtime Agent VAD Threshold (Cloud Turn Detection)</Label>
                <span className="text-xs font-mono text-muted-foreground">{serverVadThreshold.toFixed(2)}</span>
              </div>
              <input
                id="server-vad"
                type="range"
                min={0.3}
                max={0.95}
                step={0.05}
                value={serverVadThreshold}
                onChange={(e) => handleServerVadChange(parseFloat(e.target.value))}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <p className="text-xs text-muted-foreground">
                Higher = less sensitive to quiet sounds/echo
              </p>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="silence-duration" className="text-sm">Silence Duration</Label>
                <span className="text-xs font-mono text-muted-foreground">{serverSilenceDuration}ms</span>
              </div>
              <input
                id="silence-duration"
                type="range"
                min={200}
                max={1500}
                step={50}
                value={serverSilenceDuration}
                onChange={(e) => handleSilenceDurationChange(parseInt(e.target.value))}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <p className="text-xs text-muted-foreground">
                Wait time before your turn ends. Increase if AI cuts you off.
              </p>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Full mode - used in setup wizard
  return (
    <div className="space-y-6">
      {/* Restart Required Notification */}
      {restartRequired && (
        <div className="flex items-center justify-between gap-2 p-3 rounded-md bg-amber-500/10 border border-amber-500/30 text-sm">
          <div className="flex items-center gap-2">
            <RefreshCw className={`h-4 w-4 text-amber-500 shrink-0 ${isRestarting ? 'animate-spin' : ''}`} />
            <span className="text-amber-500">
              {isRestarting ? 'Restarting service...' : 'Restart required for changes to take effect'}
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRestart}
            disabled={isRestarting}
            className="border-amber-500/50 text-amber-500 hover:bg-amber-500/10"
          >
            {isRestarting ? 'Restarting...' : 'Restart'}
          </Button>
        </div>
      )}

      {/* Backend Selection */}
      <div className="space-y-3">
        <Label>Select AI Backend</Label>
        <div className="grid grid-cols-1 gap-3">
          {/* LiveKit Realtime */}
          <button
            type="button"
            onClick={() => handleBackendChange('livekit-realtime')}
            className={`p-4 text-left rounded-lg border-2 transition-all ${
              selectedBackend === 'livekit-realtime'
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="font-medium flex items-center gap-2">
                  LiveKit Realtime
                  <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-500">Recommended</span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Real-time voice AI. Multiple providers: OpenAI, Grok, Gemini.
                </p>
              </div>
              {selectedBackend === 'livekit-realtime' && (
                <Check className="h-5 w-5 text-primary shrink-0" />
              )}
            </div>
          </button>

          {/* Local AI */}
          <button
            type="button"
            onClick={() => handleBackendChange('local')}
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
              </div>
              {selectedBackend === 'local' && (
                <Check className="h-5 w-5 text-primary shrink-0" />
              )}
            </div>
          </button>
        </div>
      </div>

      {/* LiveKit Realtime Configuration */}
      {selectedBackend === 'livekit-realtime' && (
        <div className="space-y-4 pt-2 border-t">
          {/* Provider Selection */}
          {backendOptions?.providers && (
            <div className="space-y-2">
              <Label>AI Provider</Label>
              <div className="grid grid-cols-2 gap-2">
                {backendOptions.providers
                  .filter((p: Provider) => !p.coming_soon)
                  .map((provider: Provider) => (
                    <button
                      key={provider.id}
                      type="button"
                      onClick={() => handleProviderChange(provider.id)}
                      className={`p-3 text-left rounded-lg border transition-colors ${
                        selectedProvider === provider.id
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="font-medium text-sm flex items-center gap-2">
                        {provider.name}
                        {provider.recommended && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/10 text-green-500">Rec</span>
                        )}
                        {provider.configured && (
                          <Check className="h-3 w-3 text-green-500" />
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">{provider.description}</div>
                    </button>
                  ))}
              </div>
            </div>
          )}

          {/* API Key */}
          <div className="space-y-2">
            <Label htmlFor="api-key-full">{currentProviderInfo?.name || 'Provider'} API Key</Label>
            <div className="flex gap-2 items-center">
              <Input
                id="api-key-full"
                type="password"
                placeholder="Enter API key..."
                value={apiKey}
                onChange={(e) => handleKeyChange(e.target.value)}
              />
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              {keyValid && !isSaving && <Check className="h-4 w-4 text-green-500" />}
            </div>
            {keyError && (
              <p className="text-sm text-red-500 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                {keyError}
              </p>
            )}
            {keyValid && !apiKey && (
              <p className="text-sm text-green-500 flex items-center gap-1">
                <Check className="h-3 w-3" />
                API key configured
              </p>
            )}
            {currentProviderInfo?.api_key_url && (
              <p className="text-sm text-muted-foreground">
                Get API key from{' '}
                <a href={currentProviderInfo.api_key_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                  {new URL(currentProviderInfo.api_key_url).hostname}
                </a>
              </p>
            )}
          </div>

          {/* Voice Selection */}
          {voicesData?.voices && (
            <div className="space-y-2">
              <Label>Voice</Label>
              <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                {voicesData.voices.map((voice: Voice) => (
                  <button
                    key={voice.id}
                    type="button"
                    onClick={() => handleVoiceChange(voice.id)}
                    className={`p-3 text-left rounded-lg border transition-colors ${
                      selectedVoice === voice.id
                        ? 'border-primary bg-primary/10'
                        : 'border-border hover:border-primary/50'
                    }`}
                  >
                    <div className="font-medium text-sm">{voice.name}</div>
                    <div className="text-xs text-muted-foreground">{voice.description}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Local Configuration */}
      {selectedBackend === 'local' && (
        <div className="space-y-4 pt-2 border-t">
          {localConfig && (
            <div className="flex items-center gap-2 text-sm">
              <span className={`h-2 w-2 rounded-full ${localConfig.ollama?.available ? 'bg-green-500' : 'bg-yellow-500'}`} />
              <span>
                Ollama: {localConfig.ollama?.available
                  ? `Connected (${localConfig.ollama.current_model})`
                  : 'Not detected - will use default model'}
              </span>
            </div>
          )}

          {voicesData?.voices && voicesData.voices.length > 0 && (
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
                      onClick={() => handleVoiceChange(voice.id)}
                      className="flex-1 text-left"
                    >
                      <div className="font-medium text-sm">{voice.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {voice.description} - {voice.gender}
                      </div>
                    </button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handlePlayPreview(voice.id)}
                      disabled={isPlayingPreview}
                      className="ml-2"
                    >
                      {isPlayingPreview ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        'Test'
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
