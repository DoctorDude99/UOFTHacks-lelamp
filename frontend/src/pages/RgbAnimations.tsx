import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Play,
  Square,
  Loader2,
  Lightbulb,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { rgbAnimationsApi } from '@/lib/api'

export function RgbAnimations() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [currentPlaying, setCurrentPlaying] = useState<string | null>(null)
  const playingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (playingTimeoutRef.current) {
        clearTimeout(playingTimeoutRef.current)
      }
    }
  }, [])

  // Fetch animations list
  const { data: animationsData, isLoading } = useQuery({
    queryKey: ['rgb-animations'],
    queryFn: rgbAnimationsApi.list,
  })

  // Convert dictionary {name: description} to array [{name, description}]
  const animationsDict = animationsData?.animations || {}
  const animations = Object.entries(animationsDict).map(([name, description]) => ({
    name,
    description: description as string,
  }))

  // Play mutation
  const playMutation = useMutation({
    mutationFn: (name: string) => rgbAnimationsApi.play(name),
    onSuccess: (data, name) => {
      // Clear any existing timeout
      if (playingTimeoutRef.current) {
        clearTimeout(playingTimeoutRef.current)
      }

      setCurrentPlaying(name)

      // Auto-clear after animation duration (default 10s + small buffer)
      const duration = (data.duration || 10) * 1000 + 500
      playingTimeoutRef.current = setTimeout(() => {
        setCurrentPlaying(null)
      }, duration)

      queryClient.invalidateQueries({ queryKey: ['rgb-animations'] })
    },
  })

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: () => rgbAnimationsApi.stop(),
    onSuccess: () => {
      // Clear the timeout since we stopped manually
      if (playingTimeoutRef.current) {
        clearTimeout(playingTimeoutRef.current)
        playingTimeoutRef.current = null
      }
      setCurrentPlaying(null)
      queryClient.invalidateQueries({ queryKey: ['rgb-animations'] })
    },
  })

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
            <Lightbulb className="h-5 w-5 text-primary" />
            <span className="text-lg font-semibold">RGB Animations</span>
          </div>
          <div className="ml-auto">
            {currentPlaying && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
              >
                {stopMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Square className="h-4 w-4 mr-1" />
                )}
                Stop
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 p-4 max-w-2xl mx-auto w-full space-y-4">
        {/* Animations List */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Available Animations</CardTitle>
            <CardDescription>{animations.length} RGB animations</CardDescription>
          </CardHeader>
          <CardContent>
            {animations.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No RGB animations found
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
                      </div>
                      {anim.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {anim.description}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant={currentPlaying === anim.name ? 'default' : 'outline'}
                        onClick={() => playMutation.mutate(anim.name)}
                        disabled={playMutation.isPending}
                      >
                        {playMutation.isPending &&
                        playMutation.variables === anim.name ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Play className="h-4 w-4" />
                        )}
                      </Button>
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
            <CardTitle className="text-base">About RGB Animations</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>These animations control the LED ring on your LeLamp.</p>
            <p>Each animation runs for 10 seconds by default. Click the same animation again to replay it.</p>
            <p>Use the Stop button to turn off the LEDs at any time.</p>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
