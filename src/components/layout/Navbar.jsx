import { Link, useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Menu, X, CalendarDays, User, LayoutDashboard, Shield, ClipboardList } from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import Button from '../ui/Button'

export default function Navbar() {
  const { user, profile, signOut, isAdmin, isTeacher } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  const navLinks = [
    ...(user && !isTeacher && !isAdmin ? [
      { to: '/schedule',  label: 'Agendar',        icon: <ClipboardList size={16} /> },
      { to: '/dashboard', label: 'Meus Horários',  icon: <User size={16} /> },
    ] : []),
    ...(isTeacher ? [
      { to: '/teacher',  label: 'Minha Agenda',  icon: <LayoutDashboard size={16} /> },
    ] : []),
    ...(isAdmin ? [
      { to: '/admin',    label: 'Admin',          icon: <Shield size={16} /> },
    ] : []),
  ]

  const isActive = (to) => location.pathname === to

  return (
    <nav className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-100 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16">

          {/* Logo */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-blue-600 to-brand-green-500 flex items-center justify-center shadow-md">
              <CalendarDays size={18} className="text-white" />
            </div>
            <div className="hidden sm:block">
              <p className="text-sm font-bold text-brand-blue-700 leading-tight">Pan American</p>
              <p className="text-xs text-gray-400 leading-tight">Conferências</p>
            </div>
          </Link>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map(link => (
              <Link
                key={link.to}
                to={link.to}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition
                  ${isActive(link.to)
                    ? 'bg-brand-blue-50 text-brand-blue-700'
                    : 'text-gray-600 hover:text-brand-blue-700 hover:bg-gray-50'
                  }`}
              >
                {link.icon}
                {link.label}
              </Link>
            ))}
          </div>

          {/* Auth */}
          <div className="hidden md:flex items-center gap-3">
            {user ? (
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-800 leading-tight">{profile?.full_name?.split(' ')[0]}</p>
                  <p className="text-xs text-gray-400 capitalize">{profile?.role}</p>
                </div>
                <button
                  onClick={handleSignOut}
                  className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition"
                  title="Sair"
                >
                  <LogOut size={18} />
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>
                  Entrar
                </Button>
                <Button variant="primary" size="sm" onClick={() => navigate('/register')}>
                  Cadastrar
                </Button>
              </div>
            )}
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-gray-100 bg-white px-4 pb-4 pt-2 space-y-1">
          {navLinks.map(link => (
            <Link
              key={link.to}
              to={link.to}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium transition
                ${isActive(link.to)
                  ? 'bg-brand-blue-50 text-brand-blue-700'
                  : 'text-gray-700 hover:bg-gray-50'
                }`}
            >
              {link.icon}
              {link.label}
            </Link>
          ))}
          <div className="pt-2 border-t border-gray-100">
            {user ? (
              <button
                onClick={handleSignOut}
                className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-red-500 hover:bg-red-50 transition"
              >
                <LogOut size={16} /> Sair
              </button>
            ) : (
              <div className="flex gap-2 pt-1">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => { navigate('/login'); setMobileOpen(false) }}>
                  Entrar
                </Button>
                <Button variant="primary" size="sm" className="flex-1" onClick={() => { navigate('/register'); setMobileOpen(false) }}>
                  Cadastrar
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
