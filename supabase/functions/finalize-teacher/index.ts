import { corsHeaders } from '../_shared/cors.ts'

async function fetchJSON(url: string, options: RequestInit): Promise<{ ok: boolean; status: number; data: unknown }> {
  const res = await fetch(url, options)
  const text = (await res.text()).trim()
  if (!text) return { ok: res.ok, status: res.status, data: null }
  let data: unknown
  try { data = JSON.parse(text) }
  catch { throw new Error(`Resposta inválida (${res.status}): "${text.slice(0, 120)}"`) }
  return { ok: res.ok, status: res.status, data }
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
  const SERVICE_KEY  = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  const baseHeaders  = {
    'Authorization': `Bearer ${SERVICE_KEY}`,
    'apikey': SERVICE_KEY,
    'Content-Type': 'application/json',
  }

  let step = 'inicio'
  try {

    // ── 1. Identificar o usuário pelo JWT ────────────────────────
    step = 'auth'
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) throw new Error('Authorization ausente')

    const { ok: uOk, data: uData } = await fetchJSON(
      `${SUPABASE_URL}/auth/v1/user`,
      { headers: { 'Authorization': authHeader, 'apikey': SERVICE_KEY } }
    )
    if (!uOk) throw new Error('Sessão inválida')
    const user = uData as { id: string; email: string }
    if (!user?.id || !user?.email) throw new Error('Usuário não encontrado')

    const email = user.email.trim().toLowerCase()

    // ── 2. Verificar se há convite pendente para este e-mail ─────
    step = 'check_invite'
    const { data: invites } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(email)}&select=*`,
      { headers: baseHeaders }
    )
    const invite = (invites as Array<Record<string, unknown>>)?.[0]

    if (!invite) {
      // Sem convite — verifica se já é professor (finalize já rodou antes)
      const { data: teacherCheck } = await fetchJSON(
        `${SUPABASE_URL}/rest/v1/teachers?profile_id=eq.${user.id}&select=id`,
        { headers: baseHeaders }
      )
      const alreadyTeacher = (teacherCheck as Array<unknown>)?.length > 0
      return new Response(
        JSON.stringify({ success: true, no_invite: true, already_teacher: alreadyTeacher }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // ── 3. Garantir que o profile existe e tem role=teacher ──────
    step = 'upsert_profile'
    await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles`,
      {
        method: 'POST',
        headers: { ...baseHeaders, 'Prefer': 'resolution=merge-duplicates,return=minimal' },
        body: JSON.stringify({
          id:        user.id,
          email:     email,
          full_name: invite.full_name,
          role:      'teacher',
        }),
      }
    )
    // Garante role=teacher mesmo se profile já existia
    await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${user.id}`,
      {
        method: 'PATCH',
        headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
        body: JSON.stringify({ role: 'teacher', full_name: invite.full_name }),
      }
    )

    // ── 4. Verificar se teacher já existe (idempotente) ──────────
    step = 'check_teacher'
    const { data: existingTeacher } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teachers?profile_id=eq.${user.id}&select=id`,
      { headers: baseHeaders }
    )
    let teacherId = (existingTeacher as Array<{ id: string }>)?.[0]?.id ?? null

    // ── 5. Criar registro de professor se não existir ─────────────
    if (!teacherId) {
      step = 'create_teacher'
      const { ok: tOk, data: tData } = await fetchJSON(
        `${SUPABASE_URL}/rest/v1/teachers`,
        {
          method: 'POST',
          headers: { ...baseHeaders, 'Prefer': 'return=representation' },
          body: JSON.stringify({
            profile_id:   user.id,
            discipline:   invite.discipline   || null,
            room:         invite.room         || null,
            bio:          invite.bio          || null,
            grade_levels: invite.grade_levels || null,
            is_active:    true,
          }),
        }
      )
      if (tOk) {
        teacherId = (tData as Array<{ id: string }>)?.[0]?.id ?? null
      }
    }

    // ── 6. Associar matérias e turmas ────────────────────────────
    if (teacherId) {
      const subjectIds = invite.subject_ids as string[] | null
      const gradeIds   = invite.grade_ids   as string[] | null

      if (subjectIds?.length) {
        // Apaga vínculos antigos e recria (idempotente)
        await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_subjects?teacher_id=eq.${teacherId}`, {
          method: 'DELETE', headers: baseHeaders,
        })
        await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_subjects`, {
          method: 'POST',
          headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
          body: JSON.stringify(subjectIds.map(sid => ({ teacher_id: teacherId, subject_id: sid }))),
        })
      }
      if (gradeIds?.length) {
        await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_grades?teacher_id=eq.${teacherId}`, {
          method: 'DELETE', headers: baseHeaders,
        })
        await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_grades`, {
          method: 'POST',
          headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
          body: JSON.stringify(gradeIds.map(gid => ({ teacher_id: teacherId, grade_id: gid }))),
        })
      }
    }

    // ── 7. Deletar convite consumido ─────────────────────────────
    step = 'delete_invite'
    await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(email)}`,
      { method: 'DELETE', headers: baseHeaders }
    )

    return new Response(
      JSON.stringify({ success: true, role: 'teacher' }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.error(`[finalize-teacher][${step}]`, message)
    return new Response(
      JSON.stringify({ error: `[${step}] ${message}` }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
