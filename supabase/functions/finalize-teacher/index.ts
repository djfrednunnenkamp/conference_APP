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
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

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

    // ── 2. Verificar se há convite pendente para este e-mail ─────
    step = 'check_invite'
    const { data: invites } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(user.email)}&select=*`,
      { headers: baseHeaders }
    )
    const invite = (invites as Array<Record<string, unknown>>)?.[0]
    if (!invite) {
      return new Response(
        JSON.stringify({ success: true, no_invite: true }),
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
          id: user.id,
          email: user.email,
          full_name: invite.full_name,
          role: 'teacher',
        }),
      }
    )

    // ── 4. Criar registro de professor ───────────────────────────
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
      const newTeacher = (tData as Array<{ id: string }>)?.[0]
      if (newTeacher?.id) {
        const subjectIds = invite.subject_ids as string[] | null
        const gradeIds   = invite.grade_ids   as string[] | null

        if (subjectIds?.length) {
          await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_subjects`, {
            method: 'POST',
            headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
            body: JSON.stringify(subjectIds.map(sid => ({ teacher_id: newTeacher.id, subject_id: sid }))),
          })
        }
        if (gradeIds?.length) {
          await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_grades`, {
            method: 'POST',
            headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
            body: JSON.stringify(gradeIds.map(gid => ({ teacher_id: newTeacher.id, grade_id: gid }))),
          })
        }
      }
    }

    // ── 5. Deletar convite consumido ─────────────────────────────
    step = 'delete_invite'
    await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(user.email)}`,
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
