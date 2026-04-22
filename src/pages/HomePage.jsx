import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, BookOpen, MapPin, ChevronRight, CalendarDays, Users } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'

export default function HomePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [teachers, setTeachers]       = useState([])
  const [disciplines, setDisciplines] = useState([])
  const [activeEvent, setActiveEvent] = useState(null)
  const [filter, setFilter]           = useState({ search: '', discipline: '', grade: '' })
  const [loading, setLoading]         = useState(true)

  useEffect(() => {
    fetchData()
  }, [])

  async function fetchData() {
    setLoading(true)
    // Active event
    const { data: events } = await supabase
      .from('conference_events')
      .select('*')
      .eq('is_active', true)
      .order('created_at', { ascending: false })
      .limit(1)
    setActiveEvent(events?.[0] ?? null)

    // Teachers with profiles
    const { data } = await supabase
      .from('teachers')
      .select(`
        *,
        profile:profiles(full_name, email, avatar_url)
      `)
      .eq('is_active', true)
      .order('discipline')
    const list = data ?? []
    setTeachers(list)
    const uniqueDisciplines = [...new Set(list.map(t => t.discipline).filter(Boolean))]
    setDisciplines(uniqueDisciplines)
    setLoading(false)
  }

  const filtered = teachers.filter(t => {
    const name = t.profile?.full_name?.toLowerCase() ?? ''
    const disc = t.discipline?.toLowerCase() ?? ''
    const search = filter.search.toLowerCase()
    return (
      (!search || name.includes(search) || disc.includes(search)) &&
      (!filter.discipline || t.discipline === filter.discipline) &&
      (!filter.grade || (t.grade_levels ?? []).includes(filter.grade))
    )
  })

  const allGrades = [...new Set(teachers.flatMap(t => t.grade_levels ?? []))]

  return (
    <Layout>
      {/* Hero */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-blue-700 via-brand-blue-600 to-brand-green-600 px-8 py-12 mb-10 shadow-xl">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute -top-8 -right-8 w-72 h-72 rounded-full bg-white" />
          <div className="absolute bottom-0 -left-12 w-64 h-64 rounded-full bg-white" />
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-2 text-brand-blue-200 text-sm font-medium mb-3">
            <CalendarDays size={16} />
            {activeEvent ? activeEvent.name : 'Nenhuma conferência ativa no momento'}
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white leading-tight mb-3">
            Agende uma conferência<br />com o professor
          </h1>
          <p className="text-brand-blue-200 max-w-xl mb-6">
            Escolha um professor abaixo e selecione um horário disponível. Em instantes, você receberá a confirmação por e-mail.
          </p>
          {!user && (
            <div className="flex gap-3 flex-wrap">
              <Button variant="light" size="lg" onClick={() => navigate('/login')}>
                Entrar
              </Button>
              <Button
                variant="secondary"
                size="lg"
                onClick={() => navigate('/register')}
              >
                Criar conta grátis
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-8">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar professor ou disciplina…"
            value={filter.search}
            onChange={e => setFilter(f => ({ ...f, search: e.target.value }))}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 transition"
          />
        </div>
        <select
          value={filter.discipline}
          onChange={e => setFilter(f => ({ ...f, discipline: e.target.value }))}
          className="px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 transition"
        >
          <option value="">Todas as disciplinas</option>
          {disciplines.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        {allGrades.length > 0 && (
          <select
            value={filter.grade}
            onChange={e => setFilter(f => ({ ...f, grade: e.target.value }))}
            className="px-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 transition"
          >
            <option value="">Todas as turmas</option>
            {allGrades.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        )}
      </div>

      {/* Results count */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-gray-500">
          <span className="font-semibold text-gray-700">{filtered.length}</span>{' '}
          {filtered.length === 1 ? 'professor encontrado' : 'professores encontrados'}
        </p>
        <div className="flex items-center gap-1.5 text-sm text-gray-500">
          <Users size={15} />
          {teachers.length} no total
        </div>
      </div>

      {/* Teacher grid */}
      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-white rounded-2xl p-6 shadow-sm animate-pulse">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-14 h-14 rounded-2xl bg-gray-200" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-3/4" />
                  <div className="h-3 bg-gray-100 rounded w-1/2" />
                </div>
              </div>
              <div className="h-3 bg-gray-100 rounded w-full mb-2" />
              <div className="h-8 bg-gray-100 rounded-xl mt-4" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <BookOpen size={48} className="mx-auto mb-4 opacity-40" />
          <p className="text-lg font-medium">Nenhum professor encontrado</p>
          <p className="text-sm mt-1">Tente mudar os filtros de busca</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map(teacher => (
            <TeacherCard
              key={teacher.id}
              teacher={teacher}
              active={!!activeEvent}
              onBook={() => {
                if (!user) navigate('/login')
                else navigate(`/book/${teacher.id}`)
              }}
            />
          ))}
        </div>
      )}
    </Layout>
  )
}

function TeacherCard({ teacher, active, onBook }) {
  const name = teacher.profile?.full_name ?? 'Professor'
  const initials = name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()

  const gradientIndex = ['from-brand-blue-400 to-brand-blue-600',
    'from-brand-green-400 to-brand-green-600',
    'from-purple-400 to-purple-600',
    'from-orange-400 to-orange-600',
    'from-teal-400 to-teal-600',
    'from-pink-400 to-pink-600',
  ]
  const grad = gradientIndex[name.charCodeAt(0) % gradientIndex.length]

  return (
    <div className="group bg-white rounded-2xl shadow-sm hover:shadow-md border border-gray-100 transition-all duration-200 flex flex-col overflow-hidden">
      {/* Card top accent */}
      <div className={`h-1.5 bg-gradient-to-r ${grad}`} />

      <div className="p-6 flex flex-col flex-1">
        <div className="flex items-center gap-4 mb-4">
          {teacher.profile?.avatar_url ? (
            <img src={teacher.profile.avatar_url} alt={name}
              className="w-14 h-14 rounded-2xl object-cover shadow-sm" />
          ) : (
            <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${grad} flex items-center justify-center shadow-sm`}>
              <span className="text-white font-bold text-lg">{initials}</span>
            </div>
          )}
          <div className="min-w-0">
            <h3 className="font-semibold text-gray-900 leading-tight truncate">{name}</h3>
            <div className="flex items-center gap-1.5 mt-1">
              <BookOpen size={13} className="text-brand-blue-500 shrink-0" />
              <span className="text-sm text-brand-blue-600 font-medium truncate">{teacher.discipline}</span>
            </div>
          </div>
        </div>

        <div className="space-y-1.5 flex-1">
          {teacher.room && (
            <div className="flex items-center gap-1.5 text-sm text-gray-500">
              <MapPin size={13} className="shrink-0" />
              Sala {teacher.room}
            </div>
          )}
          {teacher.grade_levels?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {teacher.grade_levels.map(g => (
                <Badge key={g} variant="blue">{g}</Badge>
              ))}
            </div>
          )}
          {teacher.bio && (
            <p className="text-xs text-gray-400 mt-2 line-clamp-2">{teacher.bio}</p>
          )}
        </div>

        <Button
          variant={active ? 'primary' : 'outline'}
          size="sm"
          className="w-full mt-5 group-hover:shadow-sm"
          onClick={onBook}
          disabled={!active}
        >
          {active ? (
            <>Agendar horário <ChevronRight size={15} /></>
          ) : 'Sem conferência ativa'}
        </Button>
      </div>
    </div>
  )
}
