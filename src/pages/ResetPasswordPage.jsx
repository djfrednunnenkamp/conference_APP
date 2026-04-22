import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import toast from 'react-hot-toast'
import { CalendarDays } from 'lucide-react'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm]   = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleReset(e) {
    e.preventDefault()
    if (password !== confirm) { toast.error('Senhas não coincidem'); return }
    setLoading(true)
    const { error } = await supabase.auth.updateUser({ password })
    setLoading(false)
    if (error) { toast.error(error.message); return }
    toast.success('Senha atualizada com sucesso!')
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-blue-700 via-brand-blue-600 to-brand-green-600 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/20 backdrop-blur mb-4">
            <CalendarDays size={32} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">Pan American</h1>
        </div>
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-bold text-gray-900 mb-6">Definir nova senha</h2>
          <form onSubmit={handleReset} className="space-y-4">
            <Input label="Nova senha" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
            <Input label="Confirmar senha" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required />
            <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
              Salvar senha
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
