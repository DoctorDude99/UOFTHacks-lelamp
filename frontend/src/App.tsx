import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SetupWizard } from '@/pages/Setup'
import { Dashboard } from '@/pages/Dashboard'
import { Workflows } from '@/pages/Workflows'
import { Spotify } from '@/pages/Spotify'
import { Settings } from '@/pages/Settings'
import { Animations } from '@/pages/Animations'
import { RgbAnimations } from '@/pages/RgbAnimations'
import { ProtectedRoute } from '@/lib/auth'
import { ThemeProvider } from '@/lib/theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
    },
  },
})

function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            {/* Setup is always accessible (for first-boot wizard) */}
            <Route path="/setup" element={<SetupWizard />} />

            {/* Protected routes require authentication (unless on local network) */}
            <Route path="/dashboard" element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } />
            <Route path="/workflows" element={
              <ProtectedRoute>
                <Workflows />
              </ProtectedRoute>
            } />
            <Route path="/spotify" element={
              <ProtectedRoute>
                <Spotify />
              </ProtectedRoute>
            } />
            <Route path="/settings" element={
              <ProtectedRoute>
                <Settings />
              </ProtectedRoute>
            } />
            <Route path="/animations" element={
              <ProtectedRoute>
                <Animations />
              </ProtectedRoute>
            } />
            <Route path="/rgb-animations" element={
              <ProtectedRoute>
                <RgbAnimations />
              </ProtectedRoute>
            } />

            {/* Default redirect to dashboard */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
