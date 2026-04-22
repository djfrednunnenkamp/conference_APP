import Navbar from './Navbar'
import { isSupabaseConfigured } from '../../lib/supabase'
import { AlertTriangle } from 'lucide-react'

export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      {!isSupabaseConfigured && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5">
          <div className="max-w-7xl mx-auto flex items-center gap-2 text-amber-700 text-sm">
            <AlertTriangle size={15} className="shrink-0" />
            <span>
              <strong>Modo demonstração</strong> — Configure <code className="bg-amber-100 px-1 rounded text-xs">VITE_SUPABASE_URL</code> e{' '}
              <code className="bg-amber-100 px-1 rounded text-xs">VITE_SUPABASE_ANON_KEY</code> no arquivo <code className="bg-amber-100 px-1 rounded text-xs">.env</code> para conectar ao banco de dados.
            </span>
          </div>
        </div>
      )}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {children}
      </main>
    </div>
  )
}
