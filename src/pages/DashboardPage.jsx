import { useEffect, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { CalendarDays, Clock, MapPin, BookOpen, Trash2, UserCircle } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import toast from 'react-hot-toast'

export default function DashboardPage() {
  const { user, profile } = useAuth()
  const [bookings, setBookings] = useState([])
  const [loading, setLoading]   = useState(true)

  useEffect(() => { fetchBookings() }, [])

  async function fetchBookings() {
    setLoading(true)
    const { data } = await supabase
      .from('bookings')
      .select(`
        *,
        student:students(full_name, grade),
        time_slot:time_slots(
          start_time, end_time,
          event_day:event_days(date, event:conference_events(name)),
          teacher:teachers(
            discipline, room,
            profile:profiles(full_name)
          )
        )
      `)
      .eq('parent_id', user.id)
      .order('created_at', { ascending: false })
    setBookings(data ?? [])
    setLoading(false)
  }

  async function cancelBooking(id) {
    if (!confirm('Tem certeza que deseja cancelar este agendamento?')) return
    const { error } = await supabase.from('bookings').delete().eq('id', id)
    if (error) { toast.error(error.message); return }
    toast.success('Agendamento cancelado')
    fetchBookings()
  }

  // Group by event
  const grouped = bookings.reduce((acc, b) => {
    const eventName = b.time_slot?.event_day?.event?.name ?? 'Outros'
    if (!acc[eventName]) acc[eventName] = []
    acc[eventName].push(b)
    return acc
  }, {})

  return (
    <Layout>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Meus agendamentos</h1>
          <p className="text-gray-500 mt-1">Olá, {profile?.full_name?.split(' ')[0]}! Aqui estão todos os seus horários.</p>
        </div>
        <div className="hidden sm:flex items-center gap-2 bg-brand-blue-50 px-4 py-2 rounded-xl">
          <UserCircle size={18} className="text-brand-blue-600" />
          <span className="text-sm font-medium text-brand-blue-700">{bookings.length} agendamento{bookings.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1,2,3].map(i => (
            <div key={i} className="bg-white rounded-2xl p-6 shadow-sm animate-pulse">
              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-xl bg-gray-200" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-1/3" />
                  <div className="h-3 bg-gray-100 rounded w-1/2" />
                  <div className="h-3 bg-gray-100 rounded w-1/4" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : bookings.length === 0 ? (
        <div className="text-center py-20">
          <CalendarDays size={56} className="mx-auto text-gray-200 mb-4" />
          <h3 className="text-xl font-semibold text-gray-600 mb-2">Nenhum agendamento ainda</h3>
          <p className="text-gray-400 mb-6">Vá à lista de professores e marque uma conferência</p>
          <Button variant="primary" onClick={() => window.location.href = '/'}>
            Ver professores
          </Button>
        </div>
      ) : (
        <div className="space-y-10">
          {Object.entries(grouped).map(([eventName, items]) => (
            <div key={eventName}>
              <div className="flex items-center gap-2 mb-4">
                <CalendarDays size={18} className="text-brand-blue-500" />
                <h2 className="text-lg font-semibold text-gray-800">{eventName}</h2>
                <Badge variant="blue">{items.length}</Badge>
              </div>
              <div className="space-y-3">
                {items.map(b => (
                  <BookingCard key={b.id} booking={b} onCancel={() => cancelBooking(b.id)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  )
}

function BookingCard({ booking: b, onCancel }) {
  const ts    = b.time_slot
  const date  = ts?.event_day?.date
  const teacher = ts?.teacher

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex items-center gap-5">
      {/* Date bubble */}
      <div className="shrink-0 w-14 h-14 rounded-2xl bg-brand-blue-600 flex flex-col items-center justify-center text-white shadow-sm">
        {date && (
          <>
            <span className="text-xl font-bold leading-none">
              {format(parseISO(date), 'd')}
            </span>
            <span className="text-xs uppercase tracking-wide opacity-80">
              {format(parseISO(date), 'MMM', { locale: ptBR })}
            </span>
          </>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-gray-900 truncate">
              {teacher?.profile?.full_name ?? 'Professor'}
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
              {teacher?.discipline && (
                <span className="flex items-center gap-1 text-xs text-brand-blue-600">
                  <BookOpen size={11} />{teacher.discipline}
                </span>
              )}
              {teacher?.room && (
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  <MapPin size={11} />Sala {teacher.room}
                </span>
              )}
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <Clock size={11} />{ts?.start_time?.slice(0,5)} – {ts?.end_time?.slice(0,5)}
              </span>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="shrink-0 p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition"
            title="Cancelar"
          >
            <Trash2 size={16} />
          </button>
        </div>

        <div className="flex items-center gap-2 mt-3">
          <div className="w-5 h-5 rounded-full bg-brand-green-100 flex items-center justify-center text-xs font-bold text-brand-green-700">
            {b.student?.full_name?.[0]?.toUpperCase()}
          </div>
          <span className="text-xs text-gray-600 font-medium">{b.student?.full_name}</span>
          {b.student?.grade && <Badge variant="gray">{b.student.grade}</Badge>}
        </div>
      </div>
    </div>
  )
}
