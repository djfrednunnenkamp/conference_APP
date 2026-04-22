import { corsHeaders } from '../_shared/cors.ts'

function decodeJWT(jwt: string): Record<string, unknown> | null {
  try {
    const base64 = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64))
  } catch { return null }
}

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

    // ── 1. Autenticação ──────────────────────────────────────────
    step = 'auth'
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) throw new Error('Header Authorization ausente')
    const jwt = authHeader.replace('Bearer ', '')
    const payload = decodeJWT(jwt)
    if (!payload?.sub) throw new Error('JWT inválido ou expirado')
    const callerId = payload.sub as string

    // ── 2. Verificar admin ───────────────────────────────────────
    step = 'check_admin'
    const { ok: pOk, data: pData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${callerId}&select=role`,
      { headers: baseHeaders }
    )
    if (!pOk) throw new Error('Erro ao verificar permissões')
    const callerProfiles = pData as Array<{ role: string }>
    if (callerProfiles[0]?.role !== 'admin') throw new Error('Acesso negado')

    // ── 3. Ler body ──────────────────────────────────────────────
    step = 'body'
    const rawBody = await req.text()
    let body: Record<string, unknown>
    try { body = JSON.parse(rawBody) }
    catch { throw new Error('Body inválido') }

    const { teacher_id } = body as { teacher_id: string }
    if (!teacher_id) throw new Error('teacher_id é obrigatório')

    // ── 4. Buscar profile_id do professor ────────────────────────
    step = 'fetch_teacher'
    const { ok: tOk, data: tData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teachers?id=eq.${teacher_id}&select=id,profile_id`,
      { headers: baseHeaders }
    )
    if (!tOk) throw new Error('Erro ao buscar professor')
    const teachers = tData as Array<{ id: string; profile_id: string }>
    if (!teachers?.length) throw new Error('Professor não encontrado')
    const profileId = teachers[0].profile_id

    // ── 5. Apagar da tabela auth.users ───────────────────────────
    // Isso cascata para: profiles → teachers → teacher_subjects → teacher_grades
    // → time_slots → bookings
    step = 'delete_auth_user'
    const { ok: dOk, status: dStatus } = await fetchJSON(
      `${SUPABASE_URL}/auth/v1/admin/users/${profileId}`,
      { method: 'DELETE', headers: baseHeaders }
    )

    // 404 = usuário não existe no auth (já foi apagado antes), tudo bem
    if (!dOk && dStatus !== 404) {
      // Tenta apagar só da tabela teachers + profiles como fallback
      await fetchJSON(
        `${SUPABASE_URL}/rest/v1/teachers?id=eq.${teacher_id}`,
        { method: 'DELETE', headers: baseHeaders }
      )
      await fetchJSON(
        `${SUPABASE_URL}/rest/v1/profiles?id=eq.${profileId}`,
        { method: 'DELETE', headers: baseHeaders }
      )
    }

    // ── 6. Apagar convite pendente (se existir) ──────────────────
    step = 'delete_invite'
    const { data: profileData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${profileId}&select=email`,
      { headers: baseHeaders }
    )
    const email = (profileData as Array<{ email: string }>)?.[0]?.email
    if (email) {
      await fetchJSON(
        `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(email)}`,
        { method: 'DELETE', headers: baseHeaders }
      )
    }

    return new Response(
      JSON.stringify({ success: true }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.error(`[delete-teacher][${step}]`, message)
    return new Response(
      JSON.stringify({ error: `[${step}] ${message}` }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
