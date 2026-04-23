import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from './context/AuthContext'

import LoginPage         from './pages/LoginPage'
import RegisterPage      from './pages/RegisterPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import BookingPage       from './pages/BookingPage'
import DashboardPage     from './pages/DashboardPage'
import TeacherPage       from './pages/TeacherPage'
import AdminPage         from './pages/AdminPage'
import SchedulePage      from './pages/SchedulePage'

// Redireciona para a página correta conforme o papel do usuário
function RoleRedirect() {
  const { profile } = useAuth()
  if (profile?.role === 'admin')   return <Navigate to="/admin"     replace />
  if (profile?.role === 'teacher') return <Navigate to="/teacher"   replace />
  return <Navigate to="/dashboard" replace />
}

// Protege rota: exige login e, opcionalmente, papel específico
function ProtectedRoute({ children, roles }) {
  const { user, profile, loading } = useAuth()

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-10 h-10 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (!user) return <Navigate to="/login" replace />

  // Se o papel ainda está carregando, aguarda
  if (roles && !profile) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-10 h-10 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (roles && !roles.includes(profile?.role)) return <Navigate to="/" replace />

  return children
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              borderRadius: '12px',
              fontFamily: 'Inter, system-ui, sans-serif',
              fontSize: '14px',
            },
          }}
        />
        <Routes>
          {/* Rota raiz: redireciona para login se não autenticado,
              ou para a página do papel se autenticado */}
          <Route path="/" element={
            <ProtectedRoute>
              <RoleRedirect />
            </ProtectedRoute>
          } />

          {/* Públicas */}
          <Route path="/login"          element={<LoginPage />} />
          <Route path="/register"       element={<RegisterPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Protegidas */}
          <Route path="/book/:teacherId" element={
            <ProtectedRoute roles={['parent']}>
              <BookingPage />
            </ProtectedRoute>
          } />

          <Route path="/dashboard" element={
            <ProtectedRoute roles={['parent']}>
              <DashboardPage />
            </ProtectedRoute>
          } />

          <Route path="/schedule" element={
            <ProtectedRoute roles={['parent']}>
              <SchedulePage />
            </ProtectedRoute>
          } />

          <Route path="/teacher" element={
            <ProtectedRoute roles={['teacher']}>
              <TeacherPage />
            </ProtectedRoute>
          } />

          <Route path="/admin" element={
            <ProtectedRoute roles={['admin']}>
              <AdminPage />
            </ProtectedRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
