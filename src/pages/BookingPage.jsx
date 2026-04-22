import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { Clock, MapPin, BookOpen, CheckCircle, ChevronLeft, Plus } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import toast from 'react-hot-toast'

export default function BookingPage() {
  const { teacherId } = useParams()
  const { user, profile } = useAuth()
  const navigate = useNavigate()

  const [teacher, setTeacher]       = useState(null)
  const [eventDays, setEventDays]   = useState([])
  const [selectedDay, setSelectedDay] = useState(null)
  const [slots, setSlots]           = useState([])
  const [students, setStudents]     = useState([])
  const [loading, setLoading]       = useState(true)
  const [booking, setBooking]       = useState(false)
  const [confirmModal, setConfirmModal] = useState({ open: false, slot: null })
  const [addStudentModal, setAddStudentModal] = useState(false)
  const [newStudent, setNewStudent] = useState({ name: '', grade: '' })
  const [selectedStudent, setSelectedStudent] = useState('')

  useEffect(() => { if (!user) navigate('/login') }, [user])
  useEffect(() => { fetchTeacher() }, [teacherId])
  useEffect(() => { if (selectedDay) fetchSlots(selectedDay) }, [selectedDay])

  async function fetchTeacher() {
    setLoading(true)
    const { data: t } = await supabase
      .from('teachers')
      .select('*, profile:profiles(full_name, email, avatar_url)')
      .eq('id', teacherId)
      .single()
    setTeacher(t)

    // Active event days
    const { data: days } = await supabase
      .from('event_days')
      .select('*, event:conference_events(name, is_active)')
      .eq('event.is_active', true)
      .order('date')
    const activeDays = (days ?? []).filter(d => d.event?.is_active)
    setEventDays(activeDays)
    if (activeDays.length > 0) setSelectedDay(activeDays[0].id)

    // Students of this parent
    const { data: st } = await supabase
      .from('students')
      .select('*')
      .eq('parent_id', user.id)
      .order('full_name')
    setStudents(st ?? [])
    if (st?.length > 0) setSelectedStudent(st[0].id)

    setLoading(false)
  }

  async function fetchSlots(dayId) {
    const { data } = await supabase
      .from('time_slots')
      .select('*, bookings(id, student_id)')
      .eq('event_day_id', dayId)
      .eq('teacher_id', teacherId)
      .order('start_time')
    setSlots(data ?? [])
  }

  async function confirmBooking() {
    if (!selectedStudent) { toast.error('Selecione um aluno'); return }
    const slot = confirmModal.slot
    setBooking(true)

    // Check if parent already booked this slot for this student
    const { data: existing } = await supabase
      .from('bookings')
      .select('id')
      .eq('time_slot_id', slot.id)
      .eq('student_id', selectedStudent)
    if (existing?.length > 0) {
      toast.error('Você já agendou este horário para este aluno')
      setBooking(false)
      return
    }

    const { error } = await supabase.from('bookings').insert({
      time_slot_id: slot.id,
      student_id: selectedStudent,
      parent_id: user.id,
    })

    if (error) {
      if (error.code === '23505') toast.error('Este horário já foi reservado por outra pessoa')
      else toast.error('Erro ao agendar: ' + error.message)
      setBooking(false)
      return
    }

    toast.success('Horário agendado com sucesso!')
    setConfirmModal({ open: false, slot: null })
    setBooking(false)
    fetchSlots(selectedDay)
    navigate('/dashboard')
  }

  async function addStudent() {
    if (!newStudent.name.trim()) { toast.error('Nome é obrigatório'); return }
    const { data, error } = await supabase.from('students').insert({
      parent_id: user.id,
      full_name: newStudent.name.trim(),
      grade: newStudent.grade.trim() || null,
    }).select().single()
    if (error) { toast.error(error.message); return }
    setStudents(prev => [...prev, data])
    setSelectedStudent(data.id)
    setNewStudent({ name: '', grade: '' })
    setAddStudentModal(false)
    toast.success('Aluno adicionado!')
  }

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center py-24">
        <div className="w-10 h-10 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    </Layout>
  )

  if (!teacher) return (
    <Layout>
      <div className="text-center py-20 text-gray-400">Professor não encontrado.</div>
    </Layout>
  )

  const name = teacher.profile?.full_name ?? 'Professor'
  const initials = name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()
  const currentDay = eventDays.find(d => d.id === selectedDay)

  return (
    <Layout>
      {/* Back */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-blue-600 transition mb-6"
      >
        <ChevronLeft size={16} /> Voltar para professores
      </button>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Teacher info */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 sticky top-24">
            <div className="flex items-center gap-4 mb-5">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-blue-400 to-brand-blue-600 flex items-center justify-center shadow-sm">
                <span className="text-white font-bold text-xl">{initials}</span>
              </div>
              <div>
                <h2 className="font-bold text-gray-900">{name}</h2>
                <div className="flex items-center gap-1.5 mt-1">
                  <BookOpen size={13} className="text-brand-blue-500" />
                  <span className="text-sm text-brand-blue-600">{teacher.discipline}</span>
                </div>
              </div>
            </div>
            {teacher.room && (
              <div className="flex items-center gap-2 text-sm text-gray-600 mb-3">
                <MapPin size={14} className="text-gray-400" />
                Sala {teacher.room}
              </div>
            )}
            {teacher.grade_levels?.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {teacher.grade_levels.map(g => <Badge key={g} variant="blue">{g}</Badge>)}
              </div>
            )}
            {teacher.bio && <p className="text-sm text-gray-500 leading-relaxed">{teacher.bio}</p>}

            {/* Student selector */}
            <div className="mt-6 pt-5 border-t border-gray-100">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-gray-700">Agendar para:</p>
                <button
                  onClick={() => setAddStudentModal(true)}
                  className="text-xs text-brand-blue-600 hover:underline flex items-center gap-1"
                >
                  <Plus size={12} /> Novo aluno
                </button>
              </div>
              {students.length === 0 ? (
                <button
                  onClick={() => setAddStudentModal(true)}
                  className="w-full py-3 border-2 border-dashed border-brand-blue-200 rounded-xl text-sm text-brand-blue-600 hover:bg-brand-blue-50 transition"
                >
                  + Adicionar aluno
                </button>
              ) : (
                <div className="space-y-2">
                  {students.map(st => (
                    <button
                      key={st.id}
                      onClick={() => setSelectedStudent(st.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border-2 text-left transition
                        ${selectedStudent === st.id
                          ? 'border-brand-blue-500 bg-brand-blue-50'
                          : 'border-gray-100 hover:border-brand-blue-200'
                        }`}
                    >
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold
                        ${selectedStudent === st.id ? 'bg-brand-blue-500 text-white' : 'bg-gray-100 text-gray-600'}`}>
                        {st.full_name[0].toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800 leading-tight">{st.full_name}</p>
                        {st.grade && <p className="text-xs text-gray-400">{st.grade}</p>}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Slots */}
        <div className="lg:col-span-2">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Escolha um horário</h1>
          <p className="text-gray-500 mb-6">Horários disponíveis de 10 em 10 minutos</p>

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

          {eventDays.length === 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-6 text-center text-yellow-700">
              Nenhuma conferência ativa no momento.
            </div>
          )}

          {currentDay && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center gap-2 text-sm text-gray-500 mb-5">
                <Clock size={15} />
                {format(parseISO(currentDay.date), "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR })}
                <span className="mx-2 text-gray-300">·</span>
                {currentDay.slot_start_time?.slice(0, 5)} – {currentDay.slot_end_time?.slice(0, 5)}
              </div>

              {slots.length === 0 ? (
                <p className="text-center py-8 text-gray-400">Nenhum horário disponível neste dia.</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {slots.map(slot => {
                    const booked = slot.bookings?.length > 0
                    return (
                      <button
                        key={slot.id}
                        disabled={booked}
                        onClick={() => {
                          if (!selectedStudent) { toast.error('Selecione um aluno primeiro'); return }
                          setConfirmModal({ open: true, slot })
                        }}
                        className={`relative flex flex-col items-center justify-center py-4 rounded-xl border-2 font-semibold text-sm transition
                          ${booked
                            ? 'bg-gray-50 border-gray-100 text-gray-300 cursor-not-allowed'
                            : 'bg-white border-brand-blue-200 text-brand-blue-700 hover:bg-brand-blue-50 hover:border-brand-blue-500 hover:shadow-sm'
                          }`}
                      >
                        {booked && (
                          <span className="absolute top-1.5 right-1.5">
                            <CheckCircle size={13} className="text-gray-300" />
                          </span>
                        )}
                        <Clock size={14} className={booked ? 'text-gray-200 mb-1' : 'text-brand-blue-400 mb-1'} />
                        {slot.start_time?.slice(0, 5)}
                        {booked && <span className="text-xs font-normal mt-0.5">Ocupado</span>}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Confirm booking modal */}
      <Modal
        open={confirmModal.open}
        onClose={() => setConfirmModal({ open: false, slot: null })}
        title="Confirmar agendamento"
      >
        {confirmModal.slot && (
          <div className="space-y-5">
            <div className="bg-brand-blue-50 rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2 text-brand-blue-700">
                <BookOpen size={15} /> <span className="font-semibold">{name}</span>
              </div>
              <div className="flex items-center gap-2 text-brand-blue-600 text-sm">
                <Clock size={14} />
                {currentDay && format(parseISO(currentDay.date), "d 'de' MMMM", { locale: ptBR })}
                {' às '}
                {confirmModal.slot.start_time?.slice(0, 5)}
                {' – '}
                {confirmModal.slot.end_time?.slice(0, 5)}
              </div>
              {teacher.room && (
                <div className="flex items-center gap-2 text-brand-blue-600 text-sm">
                  <MapPin size={14} /> Sala {teacher.room}
                </div>
              )}
            </div>

            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Aluno selecionado:</p>
              <p className="font-semibold text-gray-900">
                {students.find(s => s.id === selectedStudent)?.full_name}
              </p>
            </div>

            <p className="text-xs text-gray-400">
              Você receberá uma confirmação por e-mail com os detalhes e um convite para o Google Calendar.
            </p>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setConfirmModal({ open: false, slot: null })}>
                Cancelar
              </Button>
              <Button variant="primary" className="flex-1" loading={booking} onClick={confirmBooking}>
                Confirmar
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Add student modal */}
      <Modal
        open={addStudentModal}
        onClose={() => setAddStudentModal(false)}
        title="Adicionar aluno"
        size="sm"
      >
        <div className="space-y-4">
          <Input
            label="Nome do aluno"
            placeholder="Nome completo"
            value={newStudent.name}
            onChange={e => setNewStudent(s => ({ ...s, name: e.target.value }))}
          />
          <Input
            label="Turma/Série (opcional)"
            placeholder="Ex: 8th Grade, 2º Médio…"
            value={newStudent.grade}
            onChange={e => setNewStudent(s => ({ ...s, grade: e.target.value }))}
          />
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setAddStudentModal(false)}>
              Cancelar
            </Button>
            <Button variant="primary" className="flex-1" onClick={addStudent}>
              Adicionar
            </Button>
          </div>
        </div>
      </Modal>
    </Layout>
  )
}
