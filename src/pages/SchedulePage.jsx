import { useEffect, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { CalendarDays, Clock, MapPin, BookOpen, Check, X } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import toast from 'react-hot-toast'

export default function SchedulePage() {
  const { user, profile } = useAuth()

  const [activeEvent, setActiveEvent]   = useState(null)
  const [eventDays, setEventDays]       = useState([])
  const [selectedDayId, setSelectedDayId] = useState(null)
  const [teachers, setTeachers]         = useState([])
  const [slotsByTeacher, setSlotsByTeacher] = useState({})
  const [bookingSet, setBookingSet]     = useState(new Set())
  const [myBookingSet, setMyBookingSet] = useState(new Set())
  const [loading, setLoading]           = useState(true)
  const [gridLoading, setGridLoading]   = useState(false)
  const [bookingSlot, setBookingSlot]   = useState(null)

  useEffect(() => { if (user && profile) fetchInitial() }, [user, profile])
  useEffect(() => { if (selectedDayId)  fetchGrid(selectedDayId)  }, [selectedDayId])

  async function fetchInitial() {
    setLoading(true)
    const { data: ev } = await supabase
      .from('conference_events')
      .select('id, name')
      .eq('is_active', true)
      .limit(1)
      .single()

    if (!ev) { setLoading(false); return }
    setActiveEvent(ev)

    const { data: days } = await supabase
      .from('event_days')
      .select('id, date, slot_start_time, slot_end_time')
      .eq('event_id', ev.id)
      .order('date')

    const sorted = days ?? []
    setEventDays(sorted)
    if (sorted.length > 0) setSelectedDayId(sorted[0].id)
    setLoading(false)
  }

  async function fetchGrid(dayId) {
    setGridLoading(true)

    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    if (!token) { setGridLoading(false); return }

    const res = await fetch(
      `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/get-schedule`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ event_day_id: dayId, user_id: user.id }),
      }
    )

    const payload = await res.json()
    if (!res.ok) { console.error('get-schedule error:', payload); setGridLoading(false); return }

    const allTeachers = payload.teachers ?? []
    const allSlots    = payload.slots    ?? []
    const allBookings = payload.bookings ?? []

    setTeachers(allTeachers)

    const byTeacher = {}
    const booked    = new Set()
    const mine      = new Set()

    allSlots.forEach(slot => {
      if (!byTeacher[slot.teacher_id]) byTeacher[slot.teacher_id] = []
      byTeacher[slot.teacher_id].push(slot)
    })

    allBookings.forEach(b => {
      booked.add(b.time_slot_id)
      if (b.parent_id === user.id) mine.add(b.time_slot_id)
    })

    setSlotsByTeacher(byTeacher)
    setBookingSet(booked)
    setMyBookingSet(mine)
    setGridLoading(false)
  }

  async function bookSlot(slot) {
    if (bookingSlot) return
    setBookingSlot(slot.id)

    const { error } = await supabase.from('bookings').insert({
      time_slot_id: slot.id,
      parent_id:    user.id,
    })

    if (error) {
      if (error.code === '23505') toast.error('Horário já ocupado.')
      else toast.error('Erro: ' + error.message)
    } else {
      toast.success('Horário agendado!')
      fetchGrid(selectedDayId)
    }
    setBookingSlot(null)
  }

  async function cancelSlot(slot) {
    const { error } = await supabase
      .from('bookings')
      .delete()
      .eq('time_slot_id', slot.id)
      .eq('parent_id', user.id)

    if (error) toast.error('Erro ao cancelar: ' + error.message)
    else { toast.success('Agendamento cancelado'); fetchGrid(selectedDayId) }
  }

  const selectedDay = eventDays.find(d => d.id === selectedDayId)

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center py-32">
        <div className="w-10 h-10 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    </Layout>
  )

  if (!activeEvent) return (
    <Layout>
      <div className="max-w-lg mx-auto mt-24 text-center">
        <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gray-100 flex items-center justify-center">
          <CalendarDays size={36} className="text-gray-300" />
        </div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">Nenhuma conferência ativa no momento</h2>
        <p className="text-gray-500 text-sm">Assim que uma conferência for aberta, os horários aparecerão aqui.</p>
      </div>
    </Layout>
  )

  return (
    <Layout>
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900">{activeEvent.name}</h1>
        <p className="text-gray-500 mt-1 text-sm">Clique em um horário para agendar</p>
      </div>

      {/* Day selector */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
        {eventDays.map(day => (
          <button
            key={day.id}
            onClick={() => setSelectedDayId(day.id)}
            className={`shrink-0 flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition border
              ${selectedDayId === day.id
                ? 'bg-brand-blue-600 text-white border-brand-blue-600 shadow-sm'
                : 'bg-white text-gray-600 border-gray-200 hover:border-brand-blue-400 hover:text-brand-blue-600'
              }`}
          >
            <CalendarDays size={14} />
            {format(parseISO(day.date), "EEE, d 'de' MMM", { locale: ptBR })}
          </button>
        ))}
      </div>

      {selectedDay && (
        <p className="text-xs text-gray-400 mb-5 flex items-center gap-1.5">
          <Clock size={12} />
          {format(parseISO(selectedDay.date), "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR })}
          {' · '}
          {selectedDay.slot_start_time?.slice(0, 5)} – {selectedDay.slot_end_time?.slice(0, 5)}
        </p>
      )}

      {gridLoading ? (
        <div className="flex items-center justify-center py-24">
          <div className="w-8 h-8 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : teachers.length === 0 ? (
        <div className="bg-gray-50 border border-gray-200 rounded-2xl p-10 text-center text-gray-400">
          Nenhum professor ativo encontrado.
        </div>
      ) : (
        <>
          {/* Legend */}
          <div className="flex items-center gap-5 mb-4 text-xs text-gray-500">
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 rounded border-2 border-brand-blue-300 bg-white" />
              Disponível
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 rounded bg-gray-200" />
              Ocupado
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 rounded bg-brand-green-100 border-2 border-brand-green-400" />
              Meu agendamento
            </div>
          </div>

          {/* Grid: columns = teachers, rows = header + slots (headers sincronizados) */}
          <div className="overflow-x-auto pb-4">
            <div
              className="min-w-max"
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${teachers.length}, 176px)`,
                gridTemplateRows: 'auto 1fr',
                columnGap: '12px',
                rowGap: 0,
              }}
            >
              {/* Linha 1: todos os cabeçalhos (mesma altura automaticamente) */}
              {teachers.map(teacher => {
                const name     = teacher.profile?.full_name ?? 'Professor'
                const initials = name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()
                return (
                  <div
                    key={`h-${teacher.id}`}
                    className="bg-gradient-to-b from-brand-blue-600 to-brand-blue-700 text-white p-4 rounded-t-2xl"
                  >
                    <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center font-bold text-sm mb-3">
                      {initials}
                    </div>
                    <p className="font-semibold text-sm leading-tight">{name}</p>
                    {teacher.discipline && (
                      <p className="text-xs text-brand-blue-200 mt-1 flex items-center gap-1">
                        <BookOpen size={10} />
                        {teacher.discipline}
                      </p>
                    )}
                    {teacher.room && (
                      <p className="text-xs text-brand-blue-300 mt-0.5 flex items-center gap-1">
                        <MapPin size={10} />
                        Sala {teacher.room}
                      </p>
                    )}
                  </div>
                )
              })}

              {/* Linha 2: slots de cada professor */}
              {teachers.map(teacher => {
                const slots = slotsByTeacher[teacher.id] ?? []
                return (
                  <div
                    key={`s-${teacher.id}`}
                    className="flex flex-col gap-1.5 p-2 bg-gray-50 rounded-b-2xl border border-t-0 border-gray-100 shadow-sm"
                  >
                    {slots.length === 0 && (
                      <p className="text-xs text-gray-400 text-center py-4">Sem horários</p>
                    )}
                    {slots.map(slot => {
                      const isMine    = myBookingSet.has(slot.id)
                      const isBooked  = bookingSet.has(slot.id)
                      const isLoading = bookingSlot === slot.id

                      if (isMine) return (
                        <button
                          key={slot.id}
                          onClick={() => cancelSlot(slot)}
                          title="Clique para cancelar"
                          className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-brand-green-50 border-2 border-brand-green-400 text-brand-green-700 text-xs font-semibold hover:bg-brand-green-100 transition"
                        >
                          <span>{slot.start_time?.slice(0, 5)}</span>
                          <Check size={13} strokeWidth={2.5} />
                        </button>
                      )

                      if (isBooked) return (
                        <div
                          key={slot.id}
                          className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-gray-200 text-gray-400 text-xs font-medium cursor-not-allowed"
                        >
                          <span className="line-through">{slot.start_time?.slice(0, 5)}</span>
                          <X size={12} />
                        </div>
                      )

                      return (
                        <button
                          key={slot.id}
                          onClick={() => bookSlot(slot)}
                          disabled={!!bookingSlot}
                          className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white border-2 border-brand-blue-100 text-gray-700 text-xs font-semibold hover:bg-brand-blue-50 hover:border-brand-blue-400 hover:text-brand-blue-700 transition disabled:opacity-50"
                        >
                          <span>{slot.start_time?.slice(0, 5)}</span>
                          {isLoading
                            ? <div className="w-3 h-3 border-2 border-brand-blue-400 border-t-transparent rounded-full animate-spin" />
                            : <Clock size={11} className="text-gray-400" />
                          }
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </Layout>
  )
}
