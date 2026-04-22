import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, Lock, CalendarDays } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const { signIn, resetPassword } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [forgotMode, setForgotMode] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')

  async function handleLogin(e) {
    e.preventDefault()
    setLoading(true)
    const { error } = await signIn(form.email, form.password)
    setLoading(false)
    if (error) { toast.error('E-mail ou senha inválidos'); return }
    toast.success('Bem-vindo!')
    navigate('/')
  }

  async function handleForgot(e) {
    e.preventDefault()
    setLoading(true)
    const { error } = await resetPassword(forgotEmail)
    setLoading(false)
    if (error) { toast.error('Erro ao enviar e-mail'); return }
    toast.success('Link enviado! Verifique seu e-mail.')
    setForgotMode(false)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-blue-700 via-brand-blue-600 to-brand-green-600 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/20 backdrop-blur mb-4 shadow-lg">
            <CalendarDays size={32} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">Pan American</h1>
          <p className="text-brand-blue-200 mt-1">Agenda de Conferências</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          {!forgotMode ? (
            <>
              <h2 className="text-xl font-bold text-gray-900 mb-6">Entrar na conta</h2>
              <form onSubmit={handleLogin} className="space-y-4">
                <Input
                  label="E-mail"
                  type="email"
                  placeholder="seu@email.com"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  required
                />
                <Input
                  label="Senha"
                  type="password"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  required
                />
                <button
                  type="button"
                  onClick={() => setForgotMode(true)}
                  className="text-sm text-brand-blue-600 hover:underline"
                >
                  Esqueci minha senha
                </button>
                <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full mt-2">
                  Entrar
                </Button>
              </form>
              <p className="text-center text-sm text-gray-500 mt-6">
                Não tem conta?{' '}
                <Link to="/register" className="text-brand-blue-600 font-medium hover:underline">
                  Cadastrar
                </Link>
              </p>
            </>
          ) : (
            <>
              <h2 className="text-xl font-bold text-gray-900 mb-2">Recuperar senha</h2>
              <p className="text-sm text-gray-500 mb-6">Enviaremos um link para você criar uma nova senha.</p>
              <form onSubmit={handleForgot} className="space-y-4">
                <Input
                  label="E-mail"
                  type="email"
                  placeholder="seu@email.com"
                  value={forgotEmail}
                  onChange={e => setForgotEmail(e.target.value)}
                  required
                />
                <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
                  Enviar link
                </Button>
                <button
                  type="button"
                  onClick={() => setForgotMode(false)}
                  className="w-full text-sm text-gray-500 hover:text-gray-700"
                >
                  Voltar ao login
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
