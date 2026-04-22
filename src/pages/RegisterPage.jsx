import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { CalendarDays, UserCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import toast from 'react-hot-toast'

export default function RegisterPage() {
  const { signUp } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const inviteEmail = searchParams.get('email') || ''
  const inviteName  = searchParams.get('name')  || ''
  // type=teacher (professor) | type=responsible (responsável) | sem type = professor (legado)
  const inviteType  = searchParams.get('type')  || (inviteEmail ? 'teacher' : '')
  const [form, setForm] = useState({ name: inviteName, email: inviteEmail, password: '', confirm: '' })
  const [loading, setLoading] = useState(false)

  function set(field) {
    return e => setForm(f => ({ ...f, [field]: e.target.value }))
  }

  async function handleRegister(e) {
    e.preventDefault()
    if (form.password !== form.confirm) {
      toast.error('As senhas não coincidem')
      return
    }
    if (form.password.length < 6) {
      toast.error('A senha precisa ter ao menos 6 caracteres')
      return
    }
    setLoading(true)
    const { error } = await signUp(form.email, form.password, {
      full_name: form.name,
      role: inviteType === 'teacher' ? 'teacher' : 'parent',
    })
    setLoading(false)

    if (error) {
      // Rate limit on confirmation email — account was still created
      const isRateLimit =
        error.message?.toLowerCase().includes('rate limit') ||
        error.message?.toLowerCase().includes('over_email') ||
        error.status === 429

      if (isRateLimit && inviteEmail) {
        toast.success(
          'Conta criada! O e-mail de confirmação está temporariamente indisponível. Aguarde alguns minutos e tente fazer login.',
          { duration: 8000 }
        )
        navigate('/login')
        return
      }

      toast.error(error.message)
      return
    }

    if (inviteEmail) {
      toast.success('Conta criada com sucesso! Faça login para continuar.')
    } else {
      toast.success('Conta criada! Verifique seu e-mail para confirmar.')
    }
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-blue-700 via-brand-blue-600 to-brand-green-600 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/20 backdrop-blur mb-4 shadow-lg">
            <CalendarDays size={32} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">Pan American</h1>
          <p className="text-brand-blue-200 mt-1">Agenda de Conferências</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          {inviteEmail && (
            <div className="flex items-center gap-2 bg-brand-green-50 border border-brand-green-200 rounded-xl px-4 py-3 mb-5">
              <UserCheck size={16} className="text-brand-green-600 shrink-0" />
              <p className="text-sm text-brand-green-700">
                {inviteType === 'responsible'
                  ? <>Você foi convidado como <strong>responsável</strong>. Complete o cadastro com o e-mail abaixo.</>
                  : <>Você foi convidado como <strong>professor(a)</strong>. Complete o cadastro com o e-mail abaixo.</>
                }
              </p>
            </div>
          )}
          <h2 className="text-xl font-bold text-gray-900 mb-6">Criar conta</h2>
          <form onSubmit={handleRegister} className="space-y-4">
            <Input
              label="Nome completo"
              type="text"
              placeholder="Seu nome"
              value={form.name}
              onChange={set('name')}
              readOnly={!!inviteName}
              className={inviteName ? 'bg-gray-50 cursor-not-allowed' : ''}
              required
            />
            <Input
              label="E-mail"
              type="email"
              placeholder="seu@email.com"
              value={form.email}
              onChange={set('email')}
              readOnly={!!inviteEmail}
              className={inviteEmail ? 'bg-gray-50 cursor-not-allowed' : ''}
              required
            />
            <Input
              label="Senha"
              type="password"
              placeholder="Mínimo 6 caracteres"
              value={form.password}
              onChange={set('password')}
              required
            />
            <Input
              label="Confirmar senha"
              type="password"
              placeholder="Repita a senha"
              value={form.confirm}
              onChange={set('confirm')}
              required
            />
            <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full mt-2">
              Criar conta
            </Button>
          </form>
          <p className="text-center text-sm text-gray-500 mt-6">
            Já tem conta?{' '}
            <Link to="/login" className="text-brand-blue-600 font-medium hover:underline">
              Entrar
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
