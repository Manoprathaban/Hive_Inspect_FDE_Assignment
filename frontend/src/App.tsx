import './App.css'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import AuthProvider, { useSession } from './features/auth/AuthProvider'
import { LoginPage } from './features/auth/pages/LoginPage'
import { TemplatesListPage } from './features/templates/pages/TemplatesListPage'
import { TemplateViewPage } from './features/templates/pages/TemplateViewPage'
import { LoadingState } from './features/templates/components/states/LoadingState'
import { QueryProvider } from './lib/query'

/** Router guard: no session → /login, remembering where the user was headed (§7). */
function RequireAuth() {
  const { session, isInitializing } = useSession()
  const location = useLocation()

  if (isInitializing) return <LoadingState label="Checking session…" />
  if (!session) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}

function RootRedirect() {
  const { session, isInitializing } = useSession()
  if (isInitializing) return <LoadingState label="Loading…" />
  return <Navigate to={session ? '/templates' : '/login'} replace />
}

function DevBadge() {
  const { isDevMode } = useSession()
  if (!isDevMode) return null
  return <div className="dev-badge">development session</div>
}

function AppShell() {
  return (
    <BrowserRouter>
      <div className="app">
        <DevBadge />
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/templates" element={<TemplatesListPage />} />
            <Route path="/templates/:templateId" element={<TemplateViewPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

function App() {
  return (
    <QueryProvider>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </QueryProvider>
  )
}

export default App
