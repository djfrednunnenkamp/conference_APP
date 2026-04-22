import { useEffect, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { Clock, Users, CalendarDays, UserCircle, Edit2, Check, X } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Input from '../components/ui/Input'
import toast from 'react-hot-toast'

export default function TeacherPage() {
  const { user, profile, refreshProfile } = useAuth()
  const [teacher, setTeacher]     = useState(null)
  const [eventDays, setEventDays] = useState([])
  const [selectedDay, setSelectedDay] = useState(null)
  const [slots, setSlots]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [editMode, setEditMode]   = useState(false)
  const [editForm, setEditForm]   = useState({})

  useEffect(() => { fetchTeacher() }, [])
  useEffect(() => { if (selectedDay && teacher) fetchSlots(selectedDay, teacher.id) }, [selectedDay, teacher])

  async function fetchTeacher() {
    setLoading(true)
    const { data: t } = await supabase
      .from('teachers')
      .select('*')
      .eq('profile_id', user.id)
      .single()
    setTeacher(t)
    setEditForm({
      discipline: t?.discipline ?? '',
      room: t?.room ?? '',
      bio: t?.bio ?? '',
    })

    const { data: days } = await supabase
      .from('event_days')
      .select('*, event:conference_events(name, is_active)')
      .order('date')
    const activeDays = (days ?? []).filter(d => d.event?.is_active)
    setEventDays(activeDays)
    if (activeDays.length > 0) setSelectedDay(activeDays[0].id)
    setLoading(false)
  }

  async function fetchSlots(dayId, teacherId) {
    const { data } = await supabase
      .from('time_slots')
      .select(`
        *,
        bookings(
          id,
          notes,
          student:students(full_name, grade),
          parent:profiles(full_name, email, phone)
        )
      `)
      .eq('event_day_id', dayId)
      .eq('teacher_id', teacherId)
      .order('start_time')
    setSlots(data ?? [])
  }

  async function saveProfile() {
    const { error: te } = await supabase
      .from('teachers')
      .update({ discipline: editForm.discipline, room: editForm.room, bio: editForm.bio })
      .eq('id', teacher.id)
    if (te) { toast.error(te.message); return }
    toast.success('Perfil atualizado!')
    setEditMode(false)
    setTeacher(prev => ({ ...prev, ...editForm }))
  }

  const bookedSlots  = slots.filter(s => s.bookings?.length > 0)
  const freeSlots    = slots.filter(s => !s.bookings?.length)
  const currentDay   = eventDays.find(d => d.id === selectedDay)

  return (
    <Layout>
      <div className="grid lg:grid-cols-3 gap-8">
        {/* Profile card */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 sticky top-24">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-gray-900">Meu Perfil</h2>
              {!editMode ? (
                <button
                  onClick={() => setEditMode(true)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-brand-blue-600 hover:bg-brand-blue-50 transition"
                >
                  <Edit2 size={16} />
                </button>
              ) : (
                <div className="flex gap-1">
                  <button onClick={saveProfile} className="p-1.5 rounded-lg text-green-500 hover:bg-green-50">
                    <Check size={16} />
                  </button>
                  <button onClick={() => setEditMode(false)} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100">
                    <X size={16} />
                  </button>
                </div>
              )}
            </div>

            <div className="flex items-center gap-3 mb-5">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-blue-400 to-brand-blue-600 flex items-center justify-center text-white font-bold text-xl shadow-sm">
                {profile?.full_name?.[0]?.toUpperCase()}
              </div>
              <div>
                <p className="font-semibold text-gray-900">{profile?.full_name}</p>
                <p className="text-sm text-gray-400">{profile?.email}</p>
              </div>
            </div>

            {editMode ? (
              <div className="space-y-3">
                <Input label="Disciplina" value={editForm.discipline} onChange={e => setEditForm(f => ({ ...f, discipline: e.target.value }))} />
                <Input label="Sala" value={editForm.room} onChange={e => setEditForm(f => ({ ...f, room: e.target.value }))} />
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-gray-700">Bio</label>
                  <textarea
                    rows={3}
                    value={editForm.bio}
                    onChange={e => setEditForm(f => ({ ...f, bio: e.target.value }))}
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 resize-none"
                  />
                </div>
                <Button variant="primary" size="sm" className="w-full" onClick={saveProfile}>Salvar</Button>
              </div>
            ) : (
              <div className="space-y-2 text-sm text-gray-600">
                {teacher?.discipline && <p><span className="font-medium text-gray-800">Disciplina:</span> {teacher.discipline}</p>}
                {teacher?.room && <p><span className="font-medium text-gray-800">Sala:</span> {teacher.room}</p>}
                {teacher?.bio && <p className="text-gray-500 italic leading-relaxed">{teacher.bio}</p>}
              </div>
            )}

            {/* Stats */}
            <div className="mt-6 pt-5 border-t border-gray-100 grid grid-cols-2 gap-3">
              <div className="bg-brand-blue-50 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-brand-blue-700">{bookedSlots.length}</p>
                <p className="text-xs text-brand-blue-500 mt-0.5">Agendados</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-gray-600">{freeSlots.length}</p>
                <p className="text-xs text-gray-400 mt-0.5">Disponíveis</p>
              </div>
            </div>
          </div>
        </div>

        {/* Schedule */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Minha Agenda</h1>
              <p className="text-gray-500 mt-1">Veja quem agendou horários com você</p>
            </div>
          </div>

          {/* Day tabs */}
          {eventDays.length > 1 && (
            <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
              {eventDays.map(day => (
                <button
                  key={day.id}
                  onClick={() => setSelectedDay(day.id)}
                  className={`shrink-0 px-5 py-2.5 rounded-xl text-sm font-medium transition border
                    ${selectedDay === day.id
                      ? 'bg-brand-blue-600 text-white border-brand-blue-600 shadow-sm'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-brand-blue-400'
                    }`}
                >
                  {format(parseISO(day.date), "EEE, d 'de' MMM", { locale: ptBR })}
                </button>
              ))}
            </div>
          )}

          {!currentDay && !loading && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-6 text-center text-yellow-700">
              Nenhuma conferência ativa no momento.
            </div>
          )}

          {currentDay && (
            <div className="space-y-3">
              {slots.length === 0 && (
                <p className="text-center py-12 text-gray-400">Nenhum slot configurado para este dia.</p>
              )}
              {slots.map(slot => {
                const booking = slot.bookings?.[0]
                return (
                  <div
                    key={slot.id}
                    className={`rounded-2xl border p-5 transition
                      ${booking
                        ? 'bg-white border-brand-blue-100 shadow-sm'
                        : 'bg-gray-50 border-gray-100'
                      }`}
                  >
                    <div className="flex items-center gap-4">
                      {/* Time */}
                      <div className={`shrink-0 w-16 h-16 rounded-2xl flex flex-col items-center justify-center
                        ${booking ? 'bg-brand-blue-600 shadow-sm' : 'bg-gray-200'}`}
                      >
                        <Clock size={14} className={booking ? 'text-brand-blue-200' : 'text-gray-400'} />
                        <span className={`text-sm font-bold mt-0.5 ${booking ? 'text-white' : 'text-gray-500'}`}>
                          {slot.start_time?.slice(0, 5)}
                        </span>
                      </div>

                      {booking ? (
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <UserCircle size={16} className="text-brand-blue-500" />
                            <span className="font-semibold text-gray-900">{booking.student?.full_name}</span>
                            {booking.student?.grade && <Badge variant="blue">{booking.student.grade}</Badge>}
                          </div>
                          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-xs text-gray-500">
                            <span>Responsável: {booking.parent?.full_name}</span>
                            {booking.parent?.email && <span>{booking.parent.email}</span>}
                            {booking.parent?.phone && <span>{booking.parent.phone}</span>}
                          </div>
                          {booking.notes && (
                            <p className="text-xs text-gray-400 mt-1.5 italic">{booking.notes}</p>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-gray-400">Disponível</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
