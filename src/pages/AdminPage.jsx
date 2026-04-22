import { useEffect, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  Users, CalendarDays, LayoutGrid, Plus, Trash2,
  Edit2, ChevronDown, ChevronUp, RefreshCw,
  ToggleLeft, ToggleRight, Clock, Mail, Link,
  GraduationCap, BookOpen, Tag, X, Check
} from 'lucide-react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../context/AuthContext'
import Layout from '../components/layout/Layout'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import toast from 'react-hot-toast'

const TABS = [
  { id: 'overview',    label: 'Visão Geral',  icon: <LayoutGrid size={16} /> },
  { id: 'teachers',    label: 'Professores',  icon: <Users size={16} /> },
  { id: 'students',    label: 'Alunos',       icon: <GraduationCap size={16} /> },
  { id: 'categories',  label: 'Categorias',   icon: <Tag size={16} /> },
  { id: 'events',      label: 'Conferências', icon: <CalendarDays size={16} /> },
  { id: 'bookings',    label: 'Agendamentos', icon: <Clock size={16} /> },
]

// ── Multi-checkbox component ──────────────────────────────────
function CheckboxGroup({ label, options, selected, onChange, emptyMsg }) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700 mb-2 block">{label}</label>
      <div className="border border-gray-200 rounded-xl bg-gray-50 p-3 max-h-40 overflow-y-auto">
        {options.length === 0 ? (
          <p className="text-xs text-gray-400 text-center py-2">{emptyMsg ?? 'Nenhuma opção. Adicione em Categorias.'}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {options.map(opt => {
              const checked = selected.includes(opt.id)
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onChange(checked ? selected.filter(id => id !== opt.id) : [...selected, opt.id])}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition
                    ${checked
                      ? 'bg-brand-blue-600 border-brand-blue-600 text-white'
                      : 'bg-white border-gray-200 text-gray-600 hover:border-brand-blue-400'
                    }`}
                >
                  {checked && <Check size={11} />}
                  {opt.name}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────
export default function AdminPage() {
  const { isAdmin } = useAuth()
  const [tab, setTab] = useState('overview')

  if (!isAdmin) return (
    <Layout>
      <div className="text-center py-24 text-gray-400">Acesso restrito.</div>
    </Layout>
  )

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Painel Administrativo</h1>
        <p className="text-gray-500 mt-1">Gerencie professores, alunos, conferências e agendamentos</p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-2xl p-1 mb-8 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition whitespace-nowrap
              ${tab === t.id
                ? 'bg-white text-brand-blue-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
              }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview'   && <OverviewTab />}
      {tab === 'teachers'   && <TeachersTab />}
      {tab === 'students'   && <StudentsTab />}
      {tab === 'categories' && <CategoriesTab />}
      {tab === 'events'     && <EventsTab />}
      {tab === 'bookings'   && <BookingsTab />}
    </Layout>
  )
}

// ──────────────────────────────────────────────────────────────
// OVERVIEW
// ──────────────────────────────────────────────────────────────
function OverviewTab() {
  const [stats, setStats] = useState({ teachers: 0, events: 0, bookings: 0, students: 0 })

  useEffect(() => {
    async function load() {
      const [t, e, b, s] = await Promise.all([
        supabase.from('teachers').select('id', { count: 'exact' }),
        supabase.from('conference_events').select('id', { count: 'exact' }),
        supabase.from('bookings').select('id', { count: 'exact' }),
        supabase.from('student_records').select('id', { count: 'exact' }),
      ])
      setStats({ teachers: t.count ?? 0, events: e.count ?? 0, bookings: b.count ?? 0, students: s.count ?? 0 })
    }
    load()
  }, [])

  const cards = [
    { label: 'Professores',  value: stats.teachers, color: 'from-brand-blue-500 to-brand-blue-700',   icon: <Users size={24} /> },
    { label: 'Alunos',       value: stats.students, color: 'from-orange-500 to-orange-700',            icon: <GraduationCap size={24} /> },
    { label: 'Conferências', value: stats.events,   color: 'from-brand-green-500 to-brand-green-700', icon: <CalendarDays size={24} /> },
    { label: 'Agendamentos', value: stats.bookings, color: 'from-purple-500 to-purple-700',            icon: <Clock size={24} /> },
  ]

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
      {cards.map(c => (
        <div key={c.label} className={`rounded-2xl bg-gradient-to-br ${c.color} text-white p-6 shadow-md`}>
          <div className="flex items-center justify-between mb-4">
            <div className="p-2 bg-white/20 rounded-xl">{c.icon}</div>
          </div>
          <p className="text-4xl font-extrabold">{c.value}</p>
          <p className="text-sm opacity-80 mt-1">{c.label}</p>
        </div>
      ))}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// TEACHERS
// ──────────────────────────────────────────────────────────────
function TeachersTab() {
  const [teachers, setTeachers]       = useState([])
  const [invites, setInvites]         = useState([])
  const [grades, setGrades]           = useState([])
  const [subjects, setSubjects]       = useState([])
  const [modal, setModal]             = useState(false)
  const [form, setForm]               = useState({ name: '', email: '', room: '', bio: '', subjectIds: [], gradeIds: [] })
  const [loading, setLoading]         = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null) // teacher id being confirmed
  const [deleteLoading, setDeleteLoading] = useState(false)

  useEffect(() => {
    fetchTeachers(); fetchInvites()
    supabase.from('grades').select('*').order('sort_order').order('name').then(({ data }) => setGrades(data ?? []))
    supabase.from('subjects').select('*').order('sort_order').order('name').then(({ data }) => setSubjects(data ?? []))
  }, [])

  async function fetchTeachers() {
    const { data } = await supabase
      .from('teachers')
      .select(`
        *,
        profile:profiles(full_name, email),
        teacher_subjects(subject:subjects(id, name)),
        teacher_grades(grade:grades(id, name))
      `)
      .order('created_at', { ascending: false })
    setTeachers(data ?? [])
  }

  async function fetchInvites() {
    const { data } = await supabase.from('teacher_invites').select('*').order('created_at', { ascending: false })
    setInvites(data ?? [])
  }

  function set(field) { return e => setForm(f => ({ ...f, [field]: e.target.value })) }

  async function addTeacher() {
    if (!form.name || !form.email) {
      toast.error('Nome e e-mail são obrigatórios')
      return
    }
    if (form.subjectIds.length === 0) {
      toast.error('Selecione ao menos uma matéria')
      return
    }
    setLoading(true)

    // Discipline derivada das matérias selecionadas
    const selectedSubjectNames = subjects.filter(s => form.subjectIds.includes(s.id)).map(s => s.name)
    const discipline = selectedSubjectNames.join(', ')

    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) {
      toast.error('Sessão expirada. Faça login novamente.')
      setLoading(false)
      return
    }

    let resData
    try {
      const response = await fetch(
        `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/invite-teacher`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
            'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
          },
          body: JSON.stringify({
            email:       form.email,
            full_name:   form.name,
            discipline,
            room:        form.room   || null,
            bio:         form.bio    || null,
            subject_ids: form.subjectIds,
            grade_ids:   form.gradeIds,
          }),
        }
      )
      resData = await response.json()
      if (!response.ok) throw new Error(resData?.error || `HTTP ${response.status}`)
    } catch (err) {
      setLoading(false)
      toast.error(err.message || 'Erro ao contactar o servidor')
      return
    }

    setLoading(false)
    if (resData?.rate_limited) {
      toast(resData.warning, { icon: '⚠️', duration: 8000 })
    } else if (resData?.already_active) {
      toast(resData.warning, { icon: 'ℹ️', duration: 6000 })
    } else if (resData?.restored) {
      toast.success(resData.message, { duration: 6000 })
    } else if (resData?.warning) {
      toast(resData.warning, { icon: 'ℹ️', duration: 6000 })
    } else {
      toast.success(`Convite enviado para ${form.email}!`)
    }
    setForm({ name: '', email: '', room: '', bio: '', subjectIds: [], gradeIds: [] })
    setModal(false)
    fetchInvites(); fetchTeachers()
  }

  async function deleteInvite(id) {
    const { error } = await supabase.from('teacher_invites').delete().eq('id', id)
    if (error) { toast.error(error.message); return }
    fetchInvites()
    toast.success('Convite removido')
  }

  async function toggleActive(teacher) {
    await supabase.from('teachers').update({ is_active: !teacher.is_active }).eq('id', teacher.id)
    fetchTeachers()
  }

  async function deleteTeacher(teacher) {
    const name = teacher.profile?.full_name ?? 'professor'
    setDeleteLoading(true)

    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) {
      toast.error('Sessão expirada.')
      setDeleteLoading(false)
      setConfirmDelete(null)
      return
    }

    try {
      const response = await fetch(
        `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/delete-teacher`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
            'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
          },
          body: JSON.stringify({ teacher_id: teacher.id }),
        }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data?.error || `HTTP ${response.status}`)
      toast.success(`${name} removido com sucesso`)
      setConfirmDelete(null)
      fetchTeachers()
    } catch (err) {
      toast.error(err.message || 'Erro ao remover professor')
    } finally {
      setDeleteLoading(false)
    }
  }

  function copyInviteLink(email, name) {
    const link = `${window.location.origin}/register?email=${encodeURIComponent(email)}&name=${encodeURIComponent(name)}`
    navigator.clipboard.writeText(link)
    toast.success('Link copiado!')
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-gray-500">
          {teachers.length} professor{teachers.length !== 1 ? 'es' : ''} · {invites.length} convite{invites.length !== 1 ? 's' : ''} pendente{invites.length !== 1 ? 's' : ''}
        </p>
        <Button variant="primary" size="sm" onClick={() => setModal(true)}>
          <Plus size={16} /> Adicionar professor
        </Button>
      </div>

      {/* Convites pendentes */}
      {invites.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Mail size={15} className="text-amber-500" />
            <p className="text-sm font-semibold text-amber-700">Aguardando cadastro do professor</p>
          </div>
          <div className="space-y-2">
            {invites.map(inv => (
              <div key={inv.id} className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-amber-200 flex items-center justify-center text-amber-700 font-bold text-sm shrink-0">
                  {inv.full_name[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-800 text-sm">{inv.full_name}</p>
                  <p className="text-xs text-gray-500">{inv.email} · {inv.discipline}</p>
                </div>
                <div className="text-xs text-amber-600 bg-amber-100 px-2 py-1 rounded-lg shrink-0">Pendente</div>
                <button
                  onClick={() => copyInviteLink(inv.email, inv.full_name)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-brand-blue-600 hover:bg-brand-blue-50 transition shrink-0"
                  title="Copiar link de cadastro"
                >
                  <Link size={14} />
                </button>
                <button onClick={() => deleteInvite(inv.id)} className="p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 transition shrink-0">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Professores ativos */}
      <div className="space-y-3">
        {teachers.map(t => {
          const tSubjects = t.teacher_subjects?.map(ts => ts.subject?.name).filter(Boolean) ?? []
          const tGrades   = t.teacher_grades?.map(tg => tg.grade?.name).filter(Boolean) ?? []
          return (
            <div key={t.id} className={`bg-white rounded-2xl border p-5 flex items-center gap-4 shadow-sm
              ${t.is_active ? 'border-gray-100' : 'border-gray-100 opacity-60'}`}
            >
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-blue-400 to-brand-blue-600 flex items-center justify-center text-white font-bold text-base shadow-sm shrink-0">
                {(t.profile?.full_name ?? t.id)?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-gray-900">{t.profile?.full_name ?? '—'}</p>
                  {!t.is_active && <Badge variant="gray">Inativo</Badge>}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-xs text-gray-500">
                  <span>{t.profile?.email}</span>
                  {t.room && <span>Sala {t.room}</span>}
                </div>
                {tSubjects.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tSubjects.map(s => <Badge key={s} variant="blue">{s}</Badge>)}
                  </div>
                )}
                {tGrades.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {tGrades.map(g => <Badge key={g} variant="green">{g}</Badge>)}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => toggleActive(t)}
                  className="p-2 rounded-lg text-gray-400 hover:text-brand-blue-600 hover:bg-brand-blue-50 transition"
                  title={t.is_active ? 'Desativar' : 'Ativar'}
                >
                  {t.is_active ? <ToggleRight size={20} className="text-brand-green-600" /> : <ToggleLeft size={20} />}
                </button>

                {confirmDelete === t.id ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-red-500 font-medium">Confirmar?</span>
                    <button
                      onClick={() => deleteTeacher(t)}
                      disabled={deleteLoading}
                      className="px-2 py-1 rounded-lg bg-red-500 text-white text-xs font-semibold hover:bg-red-600 transition disabled:opacity-50"
                    >
                      {deleteLoading ? '...' : 'Sim'}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="px-2 py-1 rounded-lg bg-gray-100 text-gray-600 text-xs font-semibold hover:bg-gray-200 transition"
                    >
                      Não
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(t.id)}
                    className="p-2 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition"
                    title="Remover professor"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>
          )
        })}
        {teachers.length === 0 && invites.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <Users size={40} className="mx-auto mb-3 opacity-40" />
            <p>Nenhum professor cadastrado ainda</p>
          </div>
        )}
      </div>

      {/* Modal adicionar professor */}
      <Modal open={modal} onClose={() => setModal(false)} title="Adicionar professor" size="md">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label="Nome completo *" placeholder="João da Silva" value={form.name} onChange={set('name')} />
            <Input label="E-mail *" type="email" placeholder="joao@escola.com" value={form.email} onChange={set('email')} />
          </div>
          <Input label="Sala" placeholder="101-A" value={form.room} onChange={set('room')} />
          <CheckboxGroup
            label="Matérias * (selecione uma ou mais)"
            options={subjects}
            selected={form.subjectIds}
            onChange={ids => setForm(f => ({ ...f, subjectIds: ids }))}
          />
          <CheckboxGroup
            label="Turmas (selecione uma ou mais)"
            options={grades}
            selected={form.gradeIds}
            onChange={ids => setForm(f => ({ ...f, gradeIds: ids }))}
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Bio (opcional)</label>
            <textarea
              rows={2}
              placeholder="Breve apresentação…"
              value={form.bio}
              onChange={set('bio')}
              className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 resize-none"
            />
          </div>
          <div className="bg-brand-green-50 border border-brand-green-200 rounded-xl p-3 text-xs text-brand-green-700">
            <Mail size={12} className="inline mr-1" />
            Um e-mail de convite será enviado ao professor para ele definir a senha.
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setModal(false)}>Cancelar</Button>
            <Button variant="primary" className="flex-1" loading={loading} onClick={addTeacher}>Adicionar</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// STUDENTS
// ──────────────────────────────────────────────────────────────
function StudentsTab() {
  const [students, setStudents]   = useState([])
  const [invites, setInvites]     = useState([])
  const [grades, setGrades]       = useState([])
  const [subjects, setSubjects]   = useState([])
  const [modal, setModal]         = useState(false)
  const [loading, setLoading]     = useState(false)
  const emptyForm = {
    fullName: '', gradeId: '', subjectIds: [],
    resp1Name: '', resp1Email: '',
    resp2Name: '', resp2Email: '',
    sendStudentInvite: false, studentEmail: '',
  }
  const [form, setForm] = useState(emptyForm)

  useEffect(() => {
    fetchStudents(); fetchInvites()
    supabase.from('grades').select('*').order('sort_order').order('name').then(({ data }) => setGrades(data ?? []))
    supabase.from('subjects').select('*').order('sort_order').order('name').then(({ data }) => setSubjects(data ?? []))
  }, [])

  async function fetchStudents() {
    const { data } = await supabase
      .from('student_records')
      .select(`
        *,
        grade:grades(name),
        student_record_subjects(subject:subjects(id, name)),
        student_record_responsibles(*)
      `)
      .order('full_name')
    setStudents(data ?? [])
  }

  async function fetchInvites() {
    const { data } = await supabase.from('student_invites').select('*').order('created_at', { ascending: false })
    setInvites(data ?? [])
  }

  function setF(field) { return e => setForm(f => ({ ...f, [field]: e.target.value })) }

  async function addStudent() {
    if (!form.fullName || !form.resp1Name || !form.resp1Email) {
      toast.error('Nome do aluno, responsável 1 e e-mail são obrigatórios')
      return
    }
    if (form.subjectIds.length === 0) {
      toast.error('Selecione ao menos uma matéria')
      return
    }
    if (form.sendStudentInvite && !form.studentEmail) {
      toast.error('Informe o e-mail do aluno')
      return
    }
    setLoading(true)

    try {
      // 1. Cria student_record
      const { data: sr, error: srErr } = await supabase
        .from('student_records')
        .insert({
          full_name:           form.fullName,
          grade_id:            form.gradeId || null,
          student_email:       form.sendStudentInvite ? form.studentEmail : null,
          send_student_invite: form.sendStudentInvite,
        })
        .select().single()
      if (srErr) throw new Error(srErr.message)

      // 2. Matérias
      if (form.subjectIds.length > 0) {
        await supabase.from('student_record_subjects').insert(
          form.subjectIds.map(sid => ({ student_record_id: sr.id, subject_id: sid }))
        )
      }

      // 3. Responsáveis
      const respInserts = [
        { student_record_id: sr.id, full_name: form.resp1Name, email: form.resp1Email, order_num: 1 },
      ]
      if (form.resp2Name && form.resp2Email) {
        respInserts.push({ student_record_id: sr.id, full_name: form.resp2Name, email: form.resp2Email, order_num: 2 })
      }
      await supabase.from('student_record_responsibles').insert(respInserts)

      // 4. Chama edge function para enviar e-mails
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.access_token) {
        const response = await fetch(
          `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/invite-student`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${session.access_token}`,
              'Content-Type': 'application/json',
              'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY,
            },
            body: JSON.stringify({ student_record_id: sr.id }),
          }
        )
        const resData = await response.json()

        if (resData?.rate_limited) {
          toast(`${resData.warning}`, { icon: '⚠️', duration: 8000 })
        } else if (resData?.success) {
          const sent = resData.results?.filter(r => r.status === 'sent').length ?? 0
          toast.success(`Aluno cadastrado! ${sent} convite${sent !== 1 ? 's' : ''} enviado${sent !== 1 ? 's' : ''}.`)
        } else {
          toast(`Aluno cadastrado. Erro ao enviar e-mails: ${resData?.error ?? ''}`, { icon: '⚠️' })
        }
      } else {
        toast.success('Aluno cadastrado! Use os links de convite.')
      }

      setForm(emptyForm)
      setModal(false)
      fetchStudents(); fetchInvites()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function deleteStudent(id, name) {
    if (!confirm(`Remover o aluno ${name}? Os convites e vínculos serão apagados.`)) return
    const { error } = await supabase.from('student_records').delete().eq('id', id)
    if (error) { toast.error(error.message); return }
    toast.success('Aluno removido')
    fetchStudents(); fetchInvites()
  }

  function copyLink(email, name) {
    const link = `${window.location.origin}/register?email=${encodeURIComponent(email)}&name=${encodeURIComponent(name)}`
    navigator.clipboard.writeText(link)
    toast.success('Link copiado!')
  }

  // Convites pendentes por student_record_id
  const pendingByStudent = invites.reduce((acc, inv) => {
    const sid = inv.student_record_id
    if (!acc[sid]) acc[sid] = []
    acc[sid].push(inv)
    return acc
  }, {})

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-gray-500">
          {students.length} aluno{students.length !== 1 ? 's' : ''} cadastrado{students.length !== 1 ? 's' : ''}
        </p>
        <Button variant="primary" size="sm" onClick={() => setModal(true)}>
          <Plus size={16} /> Adicionar aluno
        </Button>
      </div>

      <div className="space-y-4">
        {students.map(s => {
          const sSubjects  = s.student_record_subjects?.map(sr => sr.subject?.name).filter(Boolean) ?? []
          const responsibles = s.student_record_responsibles ?? []
          const pending    = pendingByStudent[s.id] ?? []

          return (
            <div key={s.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
              <div className="flex items-start gap-4">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white font-bold text-base shadow-sm shrink-0">
                  {s.full_name[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-gray-900">{s.full_name}</p>
                    {s.grade?.name && <Badge variant="green">{s.grade.name}</Badge>}
                  </div>
                  {sSubjects.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {sSubjects.map(sub => <Badge key={sub} variant="blue">{sub}</Badge>)}
                    </div>
                  )}

                  {/* Responsáveis */}
                  <div className="mt-3 space-y-2">
                    {responsibles.map(resp => {
                      const isPending = pending.some(p => p.email === resp.email)
                      return (
                        <div key={resp.id} className="flex items-center gap-3 text-sm">
                          <span className="text-gray-400 text-xs w-20 shrink-0">
                            Responsável {resp.order_num}
                          </span>
                          <span className="font-medium text-gray-700 truncate">{resp.full_name}</span>
                          <span className="text-gray-400 text-xs truncate">{resp.email}</span>
                          {isPending && (
                            <span className="text-xs bg-amber-100 text-amber-600 px-2 py-0.5 rounded-lg shrink-0">Pendente</span>
                          )}
                          {resp.invite_sent_at && !isPending && (
                            <span className="text-xs bg-brand-green-100 text-brand-green-600 px-2 py-0.5 rounded-lg shrink-0">Enviado</span>
                          )}
                          <button
                            onClick={() => copyLink(resp.email, resp.full_name)}
                            className="p-1 rounded-lg text-gray-300 hover:text-brand-blue-600 hover:bg-brand-blue-50 transition shrink-0"
                            title="Copiar link de cadastro"
                          >
                            <Link size={13} />
                          </button>
                        </div>
                      )
                    })}
                    {s.send_student_invite && s.student_email && (
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-gray-400 text-xs w-20 shrink-0">Aluno</span>
                        <span className="font-medium text-gray-700 truncate">{s.full_name}</span>
                        <span className="text-gray-400 text-xs truncate">{s.student_email}</span>
                        <button
                          onClick={() => copyLink(s.student_email, s.full_name)}
                          className="p-1 rounded-lg text-gray-300 hover:text-brand-blue-600 hover:bg-brand-blue-50 transition shrink-0"
                          title="Copiar link do aluno"
                        >
                          <Link size={13} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => deleteStudent(s.id, s.full_name)}
                  className="p-2 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition shrink-0"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          )
        })}

        {students.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <GraduationCap size={40} className="mx-auto mb-3 opacity-40" />
            <p>Nenhum aluno cadastrado ainda</p>
          </div>
        )}
      </div>

      {/* Modal adicionar aluno */}
      <Modal open={modal} onClose={() => { setModal(false); setForm(emptyForm) }} title="Adicionar aluno" size="md">
        <div className="space-y-4">
          {/* Dados do aluno */}
          <div className="grid grid-cols-2 gap-4">
            <Input label="Nome do aluno *" placeholder="Maria Souza" value={form.fullName} onChange={setF('fullName')} />
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">Turma</label>
              <select
                value={form.gradeId}
                onChange={setF('gradeId')}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 bg-white"
              >
                <option value="">Selecionar turma…</option>
                {grades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
          </div>

          <CheckboxGroup
            label="Matérias * (selecione todas que o aluno tem)"
            options={subjects}
            selected={form.subjectIds}
            onChange={ids => setForm(f => ({ ...f, subjectIds: ids }))}
          />

          {/* Responsável 1 */}
          <div className="border border-gray-200 rounded-xl p-4 space-y-3">
            <p className="text-sm font-semibold text-gray-700">Responsável 1 *</p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Nome" placeholder="Carlos Souza" value={form.resp1Name} onChange={setF('resp1Name')} />
              <Input label="E-mail" type="email" placeholder="carlos@email.com" value={form.resp1Email} onChange={setF('resp1Email')} />
            </div>
          </div>

          {/* Responsável 2 */}
          <div className="border border-gray-200 rounded-xl p-4 space-y-3">
            <p className="text-sm font-semibold text-gray-700">Responsável 2 <span className="text-gray-400 font-normal">(opcional)</span></p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Nome" placeholder="Ana Souza" value={form.resp2Name} onChange={setF('resp2Name')} />
              <Input label="E-mail" type="email" placeholder="ana@email.com" value={form.resp2Email} onChange={setF('resp2Email')} />
            </div>
          </div>

          {/* Toggle convite para aluno */}
          <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-xl">
            <button
              type="button"
              onClick={() => setForm(f => ({ ...f, sendStudentInvite: !f.sendStudentInvite }))}
              className="shrink-0"
            >
              {form.sendStudentInvite
                ? <ToggleRight size={26} className="text-brand-blue-600" />
                : <ToggleLeft  size={26} className="text-gray-400" />
              }
            </button>
            <div>
              <p className="text-sm font-medium text-gray-700">Enviar convite para o aluno</p>
              <p className="text-xs text-gray-400">O aluno também poderá agendar conferências</p>
            </div>
          </div>
          {form.sendStudentInvite && (
            <Input
              label="E-mail do aluno *"
              type="email"
              placeholder="maria@email.com"
              value={form.studentEmail}
              onChange={setF('studentEmail')}
            />
          )}

          <div className="bg-brand-green-50 border border-brand-green-200 rounded-xl p-3 text-xs text-brand-green-700">
            <Mail size={12} className="inline mr-1" />
            Convites serão enviados por e-mail. Em caso de limite, use o botão de copiar link.
          </div>

          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => { setModal(false); setForm(emptyForm) }}>Cancelar</Button>
            <Button variant="primary" className="flex-1" loading={loading} onClick={addStudent}>Adicionar</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// CATEGORIES
// ──────────────────────────────────────────────────────────────
function CategoriesTab() {
  const [grades, setGrades]     = useState([])
  const [subjects, setSubjects] = useState([])
  const [newGrade, setNewGrade]     = useState('')
  const [newSubject, setNewSubject] = useState('')
  const [loadingG, setLoadingG] = useState(false)
  const [loadingS, setLoadingS] = useState(false)

  useEffect(() => { fetchAll() }, [])

  async function fetchAll() {
    const [g, s] = await Promise.all([
      supabase.from('grades').select('*').order('sort_order').order('name'),
      supabase.from('subjects').select('*').order('sort_order').order('name'),
    ])
    setGrades(g.data ?? [])
    setSubjects(s.data ?? [])
  }

  async function addGrade() {
    if (!newGrade.trim()) return
    setLoadingG(true)
    const { error } = await supabase.from('grades').insert({ name: newGrade.trim() })
    setLoadingG(false)
    if (error) { toast.error(error.message); return }
    toast.success('Turma adicionada')
    setNewGrade('')
    fetchAll()
  }

  async function deleteGrade(id) {
    const { error } = await supabase.from('grades').delete().eq('id', id)
    if (error) { toast.error(error.message); return }
    fetchAll()
  }

  async function addSubject() {
    if (!newSubject.trim()) return
    setLoadingS(true)
    const { error } = await supabase.from('subjects').insert({ name: newSubject.trim() })
    setLoadingS(false)
    if (error) { toast.error(error.message); return }
    toast.success('Matéria adicionada')
    setNewSubject('')
    fetchAll()
  }

  async function deleteSubject(id) {
    const { error } = await supabase.from('subjects').delete().eq('id', id)
    if (error) { toast.error(error.message); return }
    fetchAll()
  }

  return (
    <div className="grid md:grid-cols-2 gap-6">
      {/* Turmas */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-5">
          <div className="p-2 bg-brand-green-100 rounded-xl">
            <GraduationCap size={18} className="text-brand-green-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Turmas</h3>
            <p className="text-xs text-gray-500">{grades.length} turma{grades.length !== 1 ? 's' : ''}</p>
          </div>
        </div>

        <div className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Ex: 6th Grade A"
            value={newGrade}
            onChange={e => setNewGrade(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addGrade()}
            className="flex-1 px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400"
          />
          <Button variant="primary" size="sm" loading={loadingG} onClick={addGrade}>
            <Plus size={16} />
          </Button>
        </div>

        <div className="space-y-2">
          {grades.map(g => (
            <div key={g.id} className="flex items-center justify-between px-4 py-2.5 bg-gray-50 rounded-xl">
              <span className="text-sm font-medium text-gray-700">{g.name}</span>
              <button
                onClick={() => deleteGrade(g.id)}
                className="p-1 text-gray-300 hover:text-red-400 transition rounded-lg hover:bg-red-50"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          {grades.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-6">Nenhuma turma cadastrada</p>
          )}
        </div>
      </div>

      {/* Matérias */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-5">
          <div className="p-2 bg-brand-blue-100 rounded-xl">
            <BookOpen size={18} className="text-brand-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Matérias</h3>
            <p className="text-xs text-gray-500">{subjects.length} matéria{subjects.length !== 1 ? 's' : ''}</p>
          </div>
        </div>

        <div className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Ex: Matemática"
            value={newSubject}
            onChange={e => setNewSubject(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addSubject()}
            className="flex-1 px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400"
          />
          <Button variant="primary" size="sm" loading={loadingS} onClick={addSubject}>
            <Plus size={16} />
          </Button>
        </div>

        <div className="space-y-2">
          {subjects.map(s => (
            <div key={s.id} className="flex items-center justify-between px-4 py-2.5 bg-gray-50 rounded-xl">
              <span className="text-sm font-medium text-gray-700">{s.name}</span>
              <button
                onClick={() => deleteSubject(s.id)}
                className="p-1 text-gray-300 hover:text-red-400 transition rounded-lg hover:bg-red-50"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          {subjects.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-6">Nenhuma matéria cadastrada</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// EVENTS
// ──────────────────────────────────────────────────────────────
function EventsTab() {
  const [events, setEvents]       = useState([])
  const [modal, setModal]         = useState(false)
  const [dayModal, setDayModal]   = useState({ open: false, eventId: null, eventName: '' })
  const [form, setForm]           = useState({ name: '', description: '' })
  const [dayForm, setDayForm]     = useState({ date: '', start: '18:00', end: '22:00', interval: '10' })
  const [expanded, setExpanded]   = useState({})
  const [days, setDays]           = useState({})
  const [genLoading, setGenLoading] = useState({})

  useEffect(() => { fetchEvents() }, [])

  async function fetchEvents() {
    const { data } = await supabase.from('conference_events').select('*').order('created_at', { ascending: false })
    setEvents(data ?? [])
  }

  async function toggleExpand(eventId) {
    setExpanded(prev => ({ ...prev, [eventId]: !prev[eventId] }))
    if (!days[eventId]) {
      const { data } = await supabase.from('event_days').select('*').eq('event_id', eventId).order('date')
      setDays(prev => ({ ...prev, [eventId]: data ?? [] }))
    }
  }

  async function createEvent() {
    if (!form.name) { toast.error('Nome é obrigatório'); return }
    const { error } = await supabase.from('conference_events').insert({ name: form.name, description: form.description || null })
    if (error) { toast.error(error.message); return }
    toast.success('Conferência criada!')
    setForm({ name: '', description: '' })
    setModal(false)
    fetchEvents()
  }

  async function toggleActive(event) {
    if (!event.is_active) await supabase.from('conference_events').update({ is_active: false }).neq('id', event.id)
    await supabase.from('conference_events').update({ is_active: !event.is_active }).eq('id', event.id)
    fetchEvents()
  }

  async function addDay() {
    const { eventId } = dayModal
    if (!dayForm.date) { toast.error('Data é obrigatória'); return }
    const { data: dayData, error } = await supabase.from('event_days').insert({
      event_id: eventId, date: dayForm.date,
      slot_start_time: dayForm.start, slot_end_time: dayForm.end,
      interval_minutes: parseInt(dayForm.interval),
    }).select().single()
    if (error) { toast.error(error.message); return }
    toast.success('Dia adicionado!')
    setDayModal({ open: false, eventId: null, eventName: '' })
    setDays(prev => ({ ...prev, [eventId]: [...(prev[eventId] ?? []), dayData] }))
  }

  async function generateSlots(dayId) {
    setGenLoading(prev => ({ ...prev, [dayId]: true }))
    const { error } = await supabase.rpc('generate_slots_for_day', { p_event_day_id: dayId })
    setGenLoading(prev => ({ ...prev, [dayId]: false }))
    if (error) { toast.error(error.message); return }
    toast.success('Horários gerados para todos os professores!')
  }

  async function deleteDay(dayId, eventId) {
    if (!confirm('Remover este dia? Todos os slots serão apagados.')) return
    await supabase.from('event_days').delete().eq('id', dayId)
    setDays(prev => ({ ...prev, [eventId]: (prev[eventId] ?? []).filter(d => d.id !== dayId) }))
    toast.success('Dia removido')
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-gray-500">{events.length} conferência{events.length !== 1 ? 's' : ''}</p>
        <Button variant="primary" size="sm" onClick={() => setModal(true)}>
          <Plus size={16} /> Nova conferência
        </Button>
      </div>

      <div className="space-y-4">
        {events.map(ev => (
          <div key={ev.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center gap-4 p-5">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${ev.is_active ? 'bg-brand-green-100' : 'bg-gray-100'}`}>
                <CalendarDays size={18} className={ev.is_active ? 'text-brand-green-600' : 'text-gray-400'} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-900">{ev.name}</h3>
                  {ev.is_active && <Badge variant="green">Ativa</Badge>}
                </div>
                {ev.description && <p className="text-xs text-gray-500 mt-0.5">{ev.description}</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => toggleActive(ev)} className="p-2 rounded-lg text-gray-400 hover:text-brand-green-600 hover:bg-brand-green-50 transition">
                  {ev.is_active ? <ToggleRight size={20} className="text-brand-green-600" /> : <ToggleLeft size={20} />}
                </button>
                <button onClick={() => toggleExpand(ev.id)} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition">
                  {expanded[ev.id] ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
              </div>
            </div>
            {expanded[ev.id] && (
              <div className="border-t border-gray-100 bg-gray-50 p-5 space-y-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-gray-700">Dias da conferência</p>
                  <Button variant="outline" size="sm" onClick={() => setDayModal({ open: true, eventId: ev.id, eventName: ev.name })}>
                    <Plus size={14} /> Adicionar dia
                  </Button>
                </div>
                {(days[ev.id] ?? []).length === 0 && (
                  <p className="text-sm text-gray-400 text-center py-4">Nenhum dia cadastrado</p>
                )}
                {(days[ev.id] ?? []).map(day => (
                  <div key={day.id} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-brand-blue-600 flex flex-col items-center justify-center text-white shrink-0">
                      <span className="text-lg font-bold leading-none">{format(parseISO(day.date), 'd')}</span>
                      <span className="text-xs opacity-80">{format(parseISO(day.date), 'MMM', { locale: ptBR })}</span>
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-800">
                        {format(parseISO(day.date), "EEEE, d 'de' MMMM", { locale: ptBR })}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {day.slot_start_time?.slice(0, 5)} – {day.slot_end_time?.slice(0, 5)} · a cada {day.interval_minutes} min
                      </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button variant="secondary" size="sm" loading={genLoading[day.id]} onClick={() => generateSlots(day.id)}>
                        <RefreshCw size={13} /> Gerar slots
                      </Button>
                      <button onClick={() => deleteDay(day.id, ev.id)} className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <CalendarDays size={40} className="mx-auto mb-3 opacity-40" />
            <p>Nenhuma conferência cadastrada</p>
          </div>
        )}
      </div>

      <Modal open={modal} onClose={() => setModal(false)} title="Nova conferência" size="sm">
        <div className="space-y-4">
          <Input label="Nome *" placeholder="Conferências 1º Semestre 2025" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Descrição (opcional)</label>
            <textarea rows={2} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400 resize-none" />
          </div>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setModal(false)}>Cancelar</Button>
            <Button variant="primary" className="flex-1" onClick={createEvent}>Criar</Button>
          </div>
        </div>
      </Modal>

      <Modal open={dayModal.open} onClose={() => setDayModal({ open: false, eventId: null, eventName: '' })}
        title={`Adicionar dia — ${dayModal.eventName}`} size="sm">
        <div className="space-y-4">
          <Input label="Data *" type="date" value={dayForm.date} onChange={e => setDayForm(f => ({ ...f, date: e.target.value }))} />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Início" type="time" value={dayForm.start} onChange={e => setDayForm(f => ({ ...f, start: e.target.value }))} />
            <Input label="Fim" type="time" value={dayForm.end} onChange={e => setDayForm(f => ({ ...f, end: e.target.value }))} />
          </div>
          <Input label="Intervalo (minutos)" type="number" min="5" max="60" step="5" value={dayForm.interval} onChange={e => setDayForm(f => ({ ...f, interval: e.target.value }))} />
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setDayModal({ open: false, eventId: null, eventName: '' })}>Cancelar</Button>
            <Button variant="primary" className="flex-1" onClick={addDay}>Adicionar</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────
// BOOKINGS
// ──────────────────────────────────────────────────────────────
function BookingsTab() {
  const [bookings, setBookings] = useState([])
  const [loading, setLoading]   = useState(true)
  const [filter, setFilter]     = useState('')

  useEffect(() => { fetchAll() }, [])

  async function fetchAll() {
    setLoading(true)
    const { data } = await supabase
      .from('bookings')
      .select(`
        *,
        student:students(full_name, grade),
        parent:profiles(full_name, email),
        time_slot:time_slots(
          start_time, end_time,
          event_day:event_days(date, event:conference_events(name)),
          teacher:teachers(discipline, room, profile:profiles(full_name))
        )
      `)
      .order('created_at', { ascending: false })
    setBookings(data ?? [])
    setLoading(false)
  }

  const filtered = bookings.filter(b => {
    if (!filter) return true
    const q = filter.toLowerCase()
    return (
      b.student?.full_name?.toLowerCase().includes(q) ||
      b.time_slot?.teacher?.profile?.full_name?.toLowerCase().includes(q) ||
      b.parent?.full_name?.toLowerCase().includes(q)
    )
  })

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <input
          type="text"
          placeholder="Buscar por aluno, professor ou responsável…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue-400"
        />
        <p className="shrink-0 text-sm text-gray-500">{filtered.length} resultado{filtered.length !== 1 ? 's' : ''}</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-brand-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Data', 'Horário', 'Professor', 'Aluno', 'Responsável', 'Turma'].map(h => (
                  <th key={h} className="px-4 py-3 text-left font-semibold text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((b, i) => {
                const date = b.time_slot?.event_day?.date
                return (
                  <tr key={b.id} className={`border-b border-gray-50 hover:bg-gray-50 transition ${i % 2 !== 0 ? 'bg-gray-50/40' : ''}`}>
                    <td className="px-4 py-3 font-medium text-gray-700">
                      {date ? format(parseISO(date), 'd MMM', { locale: ptBR }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{b.time_slot?.start_time?.slice(0, 5)}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{b.time_slot?.teacher?.profile?.full_name ?? '—'}</p>
                      <p className="text-xs text-gray-400">{b.time_slot?.teacher?.discipline}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{b.student?.full_name ?? '—'}</td>
                    <td className="px-4 py-3">
                      <p className="text-gray-700">{b.parent?.full_name ?? '—'}</p>
                      <p className="text-xs text-gray-400">{b.parent?.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      {b.student?.grade && <Badge variant="blue">{b.student.grade}</Badge>}
                    </td>
                  </tr>
                )
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center text-gray-400">Nenhum agendamento encontrado</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
