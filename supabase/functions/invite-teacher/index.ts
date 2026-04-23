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

    // ── 1. Autenticação ──────────────────────────────────────────
    step = 'auth'
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) throw new Error('Authorization ausente')
    const payload = decodeJWT(authHeader.replace('Bearer ', ''))
    if (!payload?.sub) throw new Error('JWT inválido')
    const userId = payload.sub as string

    // ── 2. Ler body ──────────────────────────────────────────────
    step = 'body'
    const rawBody = await req.text()
    if (!rawBody?.trim()) throw new Error('Body vazio')
    let body: Record<string, unknown>
    try { body = JSON.parse(rawBody) }
    catch { throw new Error('Body inválido') }

    const { email: rawEmail, full_name, discipline, room, bio, grade_levels, subject_ids, grade_ids } = body as {
      email: string; full_name: string; discipline?: string
      room?: string; bio?: string; grade_levels?: string[]
      subject_ids?: string[]; grade_ids?: string[]
    }
    const email = rawEmail?.trim().toLowerCase()
    if (!email || !full_name) throw new Error('email e full_name são obrigatórios')

    // ── 3. Verificar admin ───────────────────────────────────────
    step = 'check_admin'
    const { ok: pOk, data: pData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${userId}&select=role`,
      { headers: baseHeaders }
    )
    if (!pOk || (pData as Array<{ role: string }>)?.[0]?.role !== 'admin') {
      throw new Error('Acesso negado')
    }

    // ── 4. Verificar se já existe professor ativo ────────────────
    step = 'check_existing'
    const { data: existingProfiles } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?email=eq.${encodeURIComponent(email)}&select=id`,
      { headers: baseHeaders }
    )
    const existingProfileId = (existingProfiles as Array<{ id: string }>)?.[0]?.id

    if (existingProfileId) {
      const { data: existingTeachers } = await fetchJSON(
        `${SUPABASE_URL}/rest/v1/teachers?profile_id=eq.${existingProfileId}&select=id`,
        { headers: baseHeaders }
      )
      if ((existingTeachers as Array<unknown>)?.length > 0) {
        await fetchJSON(`${SUPABASE_URL}/rest/v1/profiles?id=eq.${existingProfileId}`, {
          method: 'PATCH',
          headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
          body: JSON.stringify({ full_name }),
        })
        return new Response(
          JSON.stringify({ success: true, already_active: true, warning: `${full_name} já está cadastrado e ativo.` }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }
    }

    const origin     = req.headers.get('origin') || 'http://localhost:5173'
    const redirectTo = `${origin}/reset-password`

    // ── 5. Criar usuário com email já confirmado ─────────────────
    // Garantimos email_confirm: true na criação para que o login
    // funcione imediatamente após o professor definir a senha.
    step = 'create_user'
    let invitedUserId: string | null = existingProfileId ?? null

    if (!invitedUserId) {
      const { ok: cuOk, data: cuData } = await fetchJSON(
        `${SUPABASE_URL}/auth/v1/admin/users`,
        {
          method: 'POST',
          headers: baseHeaders,
          body: JSON.stringify({
            email,
            email_confirm: true,
            user_metadata: { full_name, role: 'teacher' },
          }),
        }
      )
      if (cuOk) {
        invitedUserId = (cuData as Record<string, string>)?.id ?? null
      }
    }

    // Se o usuário já existia, garantir que o e-mail está confirmado
    if (invitedUserId) {
      step = 'confirm_email'
      await fetchJSON(`${SUPABASE_URL}/auth/v1/admin/users/${invitedUserId}`, {
        method: 'PUT',
        headers: baseHeaders,
        body: JSON.stringify({ email_confirm: true }),
      })
    }

    // ── 6. Gerar magic link para definição de senha ──────────────
    step = 'generate_link'
    const { ok: glOk, data: glData } = await fetchJSON(
      `${SUPABASE_URL}/auth/v1/admin/generate_link`,
      {
        method: 'POST',
        headers: baseHeaders,
        body: JSON.stringify({ type: 'magiclink', email, redirect_to: redirectTo }),
      }
    )

    const inviteLink = glOk
      ? ((glData as Record<string, unknown>)?.action_link as string ?? null)
      : null

    // ── 7. Salvar convite ────────────────────────────────────────
    step = 'save_invite'
    await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_invites`, {
      method: 'POST',
      headers: { ...baseHeaders, 'Prefer': 'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify({
        email, full_name,
        discipline:   discipline   || null,
        room:         room         || null,
        bio:          bio          || null,
        grade_levels: grade_levels || null,
        subject_ids:  subject_ids  || [],
        grade_ids:    grade_ids    || [],
      }),
    })

    return new Response(
      JSON.stringify({
        success: true,
        invite_link: inviteLink,
        message: `Professor adicionado. ${inviteLink ? 'Copie o link e envie para ' + email + '.' : 'Use o botão de copiar link no painel.'}`,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.error(`[invite-teacher][${step}]`, message)
    return new Response(
      JSON.stringify({ error: `[${step}] ${message}` }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
