import { useEffect, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { CalendarDays, Clock, MapPin, BookOpen, Check, X } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import toast from 'react-hot-toast'

export default function SchedulePage() {
  const { user, profile } = useAuth()

  const [activeEvent, setActiveEvent] = useState(null)
  const [eventDays, setEventDays] = useState([])
  const [selectedDayId, setSelectedDayId] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [timeColumns, setTimeColumns] = useState([])
  const [slotMap, setSlotMap] = useState({})
  const [bookingSet, setBookingSet] = useState(new Set())
  const [bookedSet, setBookedSet] = useState(new Set())
  const [students, setStudents] = useState([])
  const [selectedStudent, setSelectedStudent] = useState('')
  const [loading, setLoading] = useState(true)
  const [gridLoading, setGridLoading] = useState(false)
  const [booking, setBooking] = useState(false)
  const [confirmModal, setConfirmModal] = useState({ open: false, slot: null, teacher: null })

  useEffect(() => {
    fetchInitial()
  }, [user, profile])

  useEffect(() => {
    if (selectedDayId) fetchGrid(selectedDayId)
  }, [selectedDayId])

  async function fetchInitial() {
    if (!user || !profile) return
    setLoading(true)

    const { data: eventData } = await supabase
      .from('conference_events')
      .select('id, name, is_active')
      .eq('is_active', true)
      .limit(1)
      .single()

    if (!eventData) {
      setActiveEvent(null)
      setLoading(false)
      return
    }

    setActiveEvent(eventData)

    const { data: days } = await supabase
      .from('event_days')
      .select('id, date, slot_start_time, slot_end_time, interval_minutes')
      .eq('event_id', eventData.id)
      .order('date')

    const sortedDays = days ?? []
    setEventDays(sortedDays)
    if (sortedDays.length > 0) setSelectedDayId(sortedDays[0].id)

    const { data: responsibles } = await supabase
      .from('student_record_responsibles')
      .select('student_record_id, full_name, email, student_records(id, full_name, grade_id)')
      .eq('email', profile.email)

    const records = (responsibles ?? [])
      .filter(r => r.student_records)
      .map(r => ({
        id: r.student_records.id,
        full_name: r.student_records.full_name,
        grade_id: r.student_records.grade_id,
      }))

    const unique = Array.from(new Map(records.map(r => [r.id, r])).values())
    setStudents(unique)
    if (unique.length > 0) setSelectedStudent(unique[0].id)

    setLoading(false)
  }

  async function fetchGrid(dayId) {
    setGridLoading(true)

    const { data: teacherData } = await supabase
      .from('teachers')
      .select('id, discipline, room, profile:profiles(id, full_name)')
      .eq('is_active', true)
      .order('discipline')

    const activeTeachers = teacherData ?? []
    setTeachers(activeTeachers)

    const teacherIds = activeTeachers.map(t => t.id)

    if (teacherIds.length === 0) {
      setTimeColumns([])
      setSlotMap({})
      setBookingSet(new Set())
      setBookedSet(new Set())
      setGridLoading(false)
      return
    }

    const { data: slots } = await supabase
      .from('time_slots')
      .select('id, teacher_id, start_time, end_time, bookings(id, parent_id)')
      .eq('event_day_id', dayId)
      .in('teacher_id', teacherIds)
      .order('start_time')

    const allSlots = slots ?? []

    const timesSet = new Set()
    allSlots.forEach(s => timesSet.add(s.start_time.slice(0, 5)))
    const cols = Array.from(timesSet).sort()
    setTimeColumns(cols)

    const map = {}
    const booked = new Set()
    const myBooked = new Set()

    allSlots.forEach(slot => {
      const key = `${slot.teacher_id}__${slot.start_time.slice(0, 5)}`
      map[key] = slot
      if (slot.bookings && slot.bookings.length > 0) {
        booked.add(slot.id)
        const mine = slot.bookings.some(b => b.parent_id === user.id)
        if (mine) myBooked.add(slot.id)
      }
    })

    setSlotMap(map)
    setBookingSet(booked)
    setBookedSet(myBooked)
    setGridLoading(false)
  }

  async function handleConfirm() {
    const { slot, teacher } = confirmModal
    if (!slot) return
    setBooking(true)

    const insertPayload = {
      time_slot_id: slot.id,
      parent_id: user.id,
    }

    if (selectedStudent) {
      insertPayload.student_id = selectedStudent
    }

    const { error } = await supabase.from('bookings').insert(insertPayload)

    if (error) {
      if (error.code === '23505') {
        toast.error('Este horário já foi reservado.')
      } else if (error.code === '23502') {
        const { error: err2 } = await supabase.from('bookings').insert({
          time_slot_id: slot.id,
          parent_id: user.id,
          student_id: null,
        })
        if (err2) {
          toast.error('Erro ao agendar: ' + err2.message)
          setBooking(false)
          return
        }
      } else {
        toast.error('Erro ao agendar: ' + error.message)
        setBooking(false)
        return
      }
    }

    toast.success('Horário agendado com sucesso!')
    setConfirmModal({ open: false, slot: null, teacher: null })
    setBooking(false)
    fetchGrid(selectedDayId)
  }

  const selectedDay = eventDays.find(d => d.id === selectedDayId)

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center py-32">
          <div className="w-10 h-10 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </Layout>
    )
  }

  if (!activeEvent) {
    return (
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
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{activeEvent.name}</h1>
        <p className="text-gray-500 mt-1 text-sm">Selecione um horário disponível para agendar sua conferência</p>
      </div>

      {eventDays.length > 0 && (
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
      )}

      {selectedDay && (
        <div className="flex items-center gap-3 mb-5 text-sm text-gray-500">
          <Clock size={14} className="text-gray-400" />
          <span>{format(parseISO(selectedDay.date), "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR })}</span>
          <span className="text-gray-300">·</span>
          <span>{selectedDay.slot_start_time?.slice(0, 5)} – {selectedDay.slot_end_time?.slice(0, 5)}</span>
        </div>
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
        <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm bg-white">
          <table className="border-collapse min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="sticky left-0 z-10 bg-gray-50 px-5 py-3 text-left font-semibold text-gray-600 min-w-[220px] border-r border-gray-100">
                  Professor
                </th>
                {timeColumns.map(time => (
                  <th
                    key={time}
                    className="px-3 py-3 text-center font-semibold text-gray-600 min-w-[90px] whitespace-nowrap"
                  >
                    {time}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {teachers.map((teacher, idx) => {
                const name = teacher.profile?.full_name ?? 'Professor'
                const initials = name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()
                return (
                  <tr
                    key={teacher.id}
                    className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}
                  >
                    <td className={`sticky left-0 z-10 px-5 py-3 border-r border-gray-100 ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 shrink-0 rounded-xl bg-gradient-to-br from-brand-blue-400 to-brand-blue-600 flex items-center justify-center shadow-sm">
                          <span className="text-white font-bold text-xs">{initials}</span>
                        </div>
                        <div>
                          <p className="font-semibold text-gray-900 leading-tight">{name}</p>
                          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                            {teacher.discipline && (
                              <span className="flex items-center gap-1 text-xs text-brand-blue-600">
                                <BookOpen size={10} />
                                {teacher.discipline}
                              </span>
                            )}
                            {teacher.room && (
                              <span className="flex items-center gap-1 text-xs text-gray-400">
                                <MapPin size={10} />
                                Sala {teacher.room}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    {timeColumns.map(time => {
                      const key = `${teacher.id}__${time}`
                      const slot = slotMap[key]

                      if (!slot) {
                        return (
                          <td key={time} className="px-3 py-3 text-center">
                            <div className="w-14 h-10 mx-auto rounded-lg bg-gray-50 border border-dashed border-gray-100" />
                          </td>
                        )
                      }

                      const isBookedByMe = bookedSet.has(slot.id)
                      const isBooked = bookingSet.has(slot.id)

                      if (isBookedByMe) {
                        return (
                          <td key={time} className="px-3 py-3 text-center">
                            <div className="w-14 h-10 mx-auto rounded-lg flex items-center justify-center bg-brand-green-50 border-2 border-brand-green-400 text-brand-green-700">
                              <Check size={16} strokeWidth={2.5} />
                            </div>
                          </td>
                        )
                      }

                      if (isBooked) {
                        return (
                          <td key={time} className="px-3 py-3 text-center">
                            <div className="w-14 h-10 mx-auto rounded-lg flex items-center justify-center bg-gray-100 text-gray-300 cursor-not-allowed">
                              <X size={15} strokeWidth={2} />
                            </div>
                          </td>
                        )
                      }

                      return (
                        <td key={time} className="px-3 py-3 text-center">
                          <button
                            onClick={() => setConfirmModal({ open: true, slot, teacher })}
                            className="w-14 h-10 mx-auto rounded-lg flex items-center justify-center border-2 border-gray-100 text-gray-600 hover:bg-brand-blue-50 hover:border-brand-blue-500 hover:text-brand-blue-700 transition"
                          >
                            <Clock size={14} />
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-5 flex items-center gap-6 text-xs text-gray-500">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded border-2 border-gray-100 bg-white flex items-center justify-center">
            <Clock size={10} className="text-gray-400" />
          </div>
          Disponível
        </div>
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-gray-100 flex items-center justify-center">
            <X size={10} className="text-gray-300" />
          </div>
          Ocupado
        </div>
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-brand-green-50 border-2 border-brand-green-400 flex items-center justify-center">
            <Check size={10} className="text-brand-green-700" />
          </div>
          Agendado por mim
        </div>
      </div>

      <Modal
        open={confirmModal.open}
        onClose={() => setConfirmModal({ open: false, slot: null, teacher: null })}
        title="Confirmar agendamento"
        size="sm"
      >
        {confirmModal.slot && confirmModal.teacher && (
          <div className="space-y-5">
            <div className="bg-brand-blue-50 rounded-xl p-4 space-y-2.5">
              <div className="flex items-center gap-2 text-brand-blue-800 font-semibold">
                <BookOpen size={15} className="text-brand-blue-500 shrink-0" />
                {confirmModal.teacher.profile?.full_name ?? 'Professor'}
              </div>
              {confirmModal.teacher.discipline && (
                <div className="flex items-center gap-2 text-brand-blue-600 text-sm">
                  <span className="text-brand-blue-400 font-medium">{confirmModal.teacher.discipline}</span>
                </div>
              )}
              {confirmModal.teacher.room && (
                <div className="flex items-center gap-2 text-brand-blue-600 text-sm">
                  <MapPin size={13} className="text-brand-blue-400 shrink-0" />
                  Sala {confirmModal.teacher.room}
                </div>
              )}
              <div className="flex items-center gap-2 text-brand-blue-700 text-sm">
                <Clock size={13} className="text-brand-blue-400 shrink-0" />
                {selectedDay && format(parseISO(selectedDay.date), "d 'de' MMMM", { locale: ptBR })}
                {' às '}
                {confirmModal.slot.start_time?.slice(0, 5)}
                {confirmModal.slot.end_time ? ` – ${confirmModal.slot.end_time.slice(0, 5)}` : ''}
              </div>
            </div>

            {students.length > 1 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Agendar para qual aluno?
                </label>
                <select
                  value={selectedStudent}
                  onChange={e => setSelectedStudent(e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-brand-blue-500 focus:border-transparent"
                >
                  {students.map(s => (
                    <option key={s.id} value={s.id}>{s.full_name}</option>
                  ))}
                </select>
              </div>
            )}

            {students.length === 1 && (
              <div>
                <p className="text-sm font-medium text-gray-600">Aluno:</p>
                <p className="font-semibold text-gray-900 mt-0.5">{students[0].full_name}</p>
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setConfirmModal({ open: false, slot: null, teacher: null })}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                loading={booking}
                onClick={handleConfirm}
              >
                Confirmar
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Layout>
  )
}
