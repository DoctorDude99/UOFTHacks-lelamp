import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Play,
  Square,
  Circle,
  Trash2,
  Plus,
  Loader2,
  Clock,
  Film,
  Check,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { animationsApi } from '@/lib/api'

type RecordingState = 'idle' | 'preparing' | 'ready' | 'recording'

export function Animations() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [recordingState, setRecordingState] = useState<RecordingState>('idle')
  const [newAnimationName, setNewAnimationName] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  // Fetch animations list
  const { data: animationsData, isLoading } = useQuery({
    queryKey: ['animations'],
    queryFn: animationsApi.list,
    refetchInterval: recordingState === 'recording' ? 1000 : false,
  })

  // Fetch recording status when recording
  const { data: recordingStatus } = useQuery({
    queryKey: ['recording-status'],
    queryFn: animationsApi.getRecordingStatus,
    enabled: recordingState === 'recording',
    refetchInterval: 500,
  })

  const animations = animationsData?.animations || []
  const currentPlaying = animationsData?.current

  // Play mutation
  const playMutation = useMutation({
    mutationFn: (name: string) => animationsApi.play(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['animations'] })
    },
  })

  // Prepare record mutation
  const prepareMutation = useMutation({
    mutationFn: () => animationsApi.prepareRecord(),
    onSuccess: () => {
      setRecordingState('ready')
      // Auto-transition after motors release (3.5s)
      setTimeout(() => {
        if (recordingState === 'preparing') {
          setRecordingState('ready')
        }
      }, 3500)
    },
  })

  // Start record mutation
  const startRecordMutation = useMutation({
    mutationFn: (name: string) => animationsApi.startRecord(name),
    onSuccess: () => {
      setRecordingState('recording')
    },
    onError: () => {
      setRecordingState('ready')
    },
  })

  // Stop record mutation
  const stopRecordMutation = useMutation({
    mutationFn: () => animationsApi.stopRecord(),
    onSuccess: () => {
      setRecordingState('idle')
      setNewAnimationName('')
      queryClient.invalidateQueries({ queryKey: ['animations'] })
    },
    onError: () => {
      setRecordingState('idle')
    },
  })

  // Cancel record mutation
  const cancelMutation = useMutation({
    mutationFn: () => animationsApi.cancelRecord(),
    onSuccess: () => {
      setRecordingState('idle')
      setNewAnimationName('')
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (name: string) => animationsApi.delete(name),
    onSuccess: () => {
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['animations'] })
    },
  })

  const handleNewRecording = () => {
    setRecordingState('preparing')
    prepareMutation.mutate()
  }

  const handleStartRecording = () => {
    if (newAnimationName.trim()) {
      startRecordMutation.mutate(newAnimationName.trim())
    }
  }

  const handleStopRecording = () => {
    stopRecordMutation.mutate()
  }

  const handleCancelRecording = () => {
    cancelMutation.mutate()
  }

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const mins = Math.floor(seconds / 60)
    const secs = (seconds % 60).toFixed(0)
    return `${mins}m ${secs}s`
  }

  const protectedAnimations = ['idle', 'sleep', 'wake_up']

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
            <Film className="h-5 w-5 text-primary" />
            <span className="text-lg font-semibold">Animations</span>
          </div>
          <div className="ml-auto">
            {recordingState === 'idle' && (
              <Button size="sm" onClick={handleNewRecording}>
                <Plus className="h-4 w-4 mr-1" />
                New Recording
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 p-4 max-w-2xl mx-auto w-full space-y-4">
        {/* Recording Panel */}
        {recordingState !== 'idle' && (
          <Card className="border-primary">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                {recordingState === 'recording' ? (
                  <>
                    <Circle className="h-4 w-4 text-red-500 animate-pulse fill-red-500" />
                    Recording...
                  </>
                ) : recordingState === 'preparing' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Preparing...
                  </>
                ) : (
                  <>
                    <Circle className="h-4 w-4" />
                    Ready to Record
                  </>
                )}
              </CardTitle>
              <CardDescription>
                {recordingState === 'preparing'
                  ? 'Moving to neutral position and releasing motors...'
                  : recordingState === 'ready'
                  ? 'Motors released. Move the lamp to create your animation.'
                  : `Recording: ${recordingStatus?.frames || 0} frames (${formatDuration(
                      recordingStatus?.duration || 0
                    )})`}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {(recordingState === 'ready' || recordingState === 'preparing') && (
                <div className="space-y-2">
                  <Input
                    placeholder="Animation name (e.g., happy_dance)"
                    value={newAnimationName}
                    onChange={(e) => setNewAnimationName(e.target.value)}
                    disabled={recordingState === 'preparing'}
                  />
                  <p className="text-xs text-muted-foreground">
                    Use lowercase letters, numbers, and underscores
                  </p>
                </div>
              )}

              <div className="flex gap-2">
                {recordingState === 'ready' && (
                  <>
                    <Button
                      onClick={handleStartRecording}
                      disabled={!newAnimationName.trim() || startRecordMutation.isPending}
                      className="flex-1"
                    >
                      {startRecordMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      ) : (
                        <Circle className="h-4 w-4 mr-1 fill-red-500 text-red-500" />
                      )}
                      Start Recording
                    </Button>
                    <Button variant="outline" onClick={handleCancelRecording}>
                      <X className="h-4 w-4 mr-1" />
                      Cancel
                    </Button>
                  </>
                )}

                {recordingState === 'recording' && (
                  <Button
                    onClick={handleStopRecording}
                    disabled={stopRecordMutation.isPending}
                    variant="destructive"
                    className="flex-1"
                  >
                    {stopRecordMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    ) : (
                      <Square className="h-4 w-4 mr-1" />
                    )}
                    Stop & Save
                  </Button>
                )}

                {recordingState === 'preparing' && (
                  <Button
                    variant="outline"
                    onClick={handleCancelRecording}
                    disabled={cancelMutation.isPending}
                  >
                    <X className="h-4 w-4 mr-1" />
                    Cancel
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Animations List */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Available Animations</CardTitle>
            <CardDescription>{animations.length} animations</CardDescription>
          </CardHeader>
          <CardContent>
            {animations.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No animations found
              </p>
            ) : (
              <div className="space-y-2">
                {animations.map((anim) => (
                  <div
                    key={anim.name}
                    className={`flex items-center gap-3 p-3 rounded-lg border ${
                      currentPlaying === anim.name
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{anim.name}</span>
                        {currentPlaying === anim.name && (
                          <span className="text-xs bg-primary text-primary-foreground px-1.5 py-0.5 rounded">
                            Playing
                          </span>
                        )}
                        {protectedAnimations.includes(anim.name) && (
                          <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                            System
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatDuration(anim.duration)}
                        </span>
                        <span>{anim.frames} frames</span>
                        <span>{anim.size_kb} KB</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant={currentPlaying === anim.name ? 'default' : 'outline'}
                        onClick={() => playMutation.mutate(anim.name)}
                        disabled={playMutation.isPending || recordingState !== 'idle'}
                      >
                        {playMutation.isPending &&
                        playMutation.variables === anim.name ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Play className="h-4 w-4" />
                        )}
                      </Button>

                      {!protectedAnimations.includes(anim.name) && (
                        <>
                          {deleteConfirm === anim.name ? (
                            <div className="flex items-center gap-1">
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={() => deleteMutation.mutate(anim.name)}
                                disabled={deleteMutation.isPending}
                              >
                                <Check className="h-4 w-4" />
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setDeleteConfirm(null)}
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setDeleteConfirm(anim.name)}
                              disabled={recordingState !== 'idle'}
                            >
                              <Trash2 className="h-4 w-4 text-muted-foreground" />
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Tips */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recording Tips</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>1. Click "New Recording" to prepare - the lamp will move to a neutral position</p>
            <p>2. Once motors are released, physically move the lamp through your animation</p>
            <p>3. Click "Stop & Save" when done - the animation will be saved at 30 FPS</p>
            <p>4. Keep recordings under 10 seconds for best results</p>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
