import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider, useAuth } from './lib/auth'
import { authApi, setAuthTokenGetter } from './lib/api'

interface AuthConfig {
  enabled: boolean
  localBypass: boolean
  clerkPublishableKey: string | null
}

// Component to set the auth token getter for API calls
function AuthTokenSetter() {
  const { getToken } = useAuth()

  useEffect(() => {
    setAuthTokenGetter(getToken)
  }, [getToken])

  return null
}

function AppWrapper() {
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)

  useEffect(() => {
    // Fetch auth config from backend
    authApi.getConfig()
      .then((config) => {
        setAuthConfig({
          enabled: config.enabled,
          localBypass: config.localBypass,
          clerkPublishableKey: config.clerkPublishableKey,
        })
      })
      .catch((err) => {
        console.error('Failed to fetch auth config:', err)
        // Default to auth disabled on error
        setAuthConfig({
          enabled: false,
          localBypass: true,
          clerkPublishableKey: null,
        })
      })
  }, [])

  if (!authConfig) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-white">Loading...</div>
      </div>
    )
  }

  return (
    <AuthProvider config={authConfig}>
      <AuthTokenSetter />
      <App />
    </AuthProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppWrapper />
  </StrictMode>,
)
