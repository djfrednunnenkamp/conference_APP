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
  catch { throw new Error(`Resposta inválida de ${url} (${res.status}): "${text.slice(0, 120)}"`) }
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

    // ── 1. Autenticação ─────────────────────────────────────────
    step = 'auth'
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) throw new Error('Header Authorization ausente')
    const jwt = authHeader.replace('Bearer ', '')
    const payload = decodeJWT(jwt)
    if (!payload?.sub) throw new Error('JWT inválido ou expirado')
    const userId = payload.sub as string

    // ── 2. Ler body ─────────────────────────────────────────────
    step = 'body'
    const rawBody = await req.text()
    if (!rawBody?.trim()) throw new Error('Body vazio')
    let body: Record<string, unknown>
    try { body = JSON.parse(rawBody) }
    catch { throw new Error(`Body inválido: "${rawBody.slice(0, 80)}"`) }

    const { student_record_id } = body as { student_record_id: string }
    if (!student_record_id) throw new Error('student_record_id é obrigatório')

    // ── 3. Verificar admin ──────────────────────────────────────
    step = 'check_admin'
    const { ok: pOk, status: pStatus, data: pData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${userId}&select=role`,
      { headers: baseHeaders }
    )
    if (!pOk) throw new Error(`REST profiles erro ${pStatus}: ${JSON.stringify(pData).slice(0, 100)}`)
    const profiles = pData as Array<{ role: string }>
    if (!Array.isArray(profiles) || profiles[0]?.role !== 'admin') {
      throw new Error(`Acesso negado (role="${profiles[0]?.role ?? 'nenhum'}")`)
    }

    // ── 4. Buscar dados do aluno e responsáveis ─────────────────
    step = 'fetch_student'
    const { ok: sOk, status: sStatus, data: sData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/student_records?id=eq.${student_record_id}&select=*`,
      { headers: baseHeaders }
    )
    if (!sOk) throw new Error(`Erro ao buscar aluno (${sStatus})`)
    const students = sData as Array<Record<string, unknown>>
    if (!students?.length) throw new Error('Aluno não encontrado')
    const student = students[0]

    const { ok: rOk, data: rData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/student_record_responsibles?student_record_id=eq.${student_record_id}&order=order_num`,
      { headers: baseHeaders }
    )
    if (!rOk) throw new Error('Erro ao buscar responsáveis')
    const responsibles = rData as Array<{ id: string; email: string; full_name: string; order_num: number }>

    // ── 5. Enviar convites ──────────────────────────────────────
    step = 'send_invites'
    const origin     = req.headers.get('origin') || 'http://localhost:5174'
    const redirectTo = `${origin}/reset-password`

    const results: Array<{ email: string; status: 'sent' | 'exists' | 'rate_limited' | 'error'; message?: string }> = []
    let anyRateLimited = false

    // Invites para responsáveis
    for (const resp of responsibles) {
      // Salva em student_invites
      await fetchJSON(
        `${SUPABASE_URL}/rest/v1/student_invites`,
        {
          method: 'POST',
          headers: { ...baseHeaders, 'Prefer': 'resolution=merge-duplicates' },
          body: JSON.stringify({
            email: resp.email,
            full_name: resp.full_name,
            student_record_id,
            invite_type: 'responsible',
          }),
        }
      )

      // Envia e-mail
      const { ok: iOk, status: iStatus, data: iData } = await fetchJSON(
        `${SUPABASE_URL}/auth/v1/invite`,
        {
          method: 'POST',
          headers: baseHeaders,
          body: JSON.stringify({
            email: resp.email,
            data: { full_name: resp.full_name, role: 'parent' },
            redirect_to: redirectTo,
          }),
        }
      )

      if (!iOk) {
        const errMsg = ((iData as Record<string, string>)?.msg ?? (iData as Record<string, string>)?.message ?? '').toLowerCase()
        if (errMsg.includes('already') || errMsg.includes('registered') || errMsg.includes('exists')) {
          results.push({ email: resp.email, status: 'exists' })
        } else if (iStatus === 429 || errMsg.includes('rate limit') || errMsg.includes('over_email')) {
          results.push({ email: resp.email, status: 'rate_limited' })
          anyRateLimited = true
        } else {
          results.push({ email: resp.email, status: 'error', message: errMsg })
        }
      } else {
        // Marca como enviado
        await fetchJSON(
          `${SUPABASE_URL}/rest/v1/student_record_responsibles?id=eq.${resp.id}`,
          {
            method: 'PATCH',
            headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
            body: JSON.stringify({ invite_sent_at: new Date().toISOString() }),
          }
        )
        results.push({ email: resp.email, status: 'sent' })
      }
    }

    // Invite para o aluno (se configurado)
    if (student.send_student_invite && student.student_email) {
      const studentEmail = student.student_email as string
      const studentName  = student.full_name as string

      await fetchJSON(
        `${SUPABASE_URL}/rest/v1/student_invites`,
        {
          method: 'POST',
          headers: { ...baseHeaders, 'Prefer': 'resolution=merge-duplicates' },
          body: JSON.stringify({
            email: studentEmail,
            full_name: studentName,
            student_record_id,
            invite_type: 'student',
          }),
        }
      )

      const { ok: iOk, status: iStatus, data: iData } = await fetchJSON(
        `${SUPABASE_URL}/auth/v1/invite`,
        {
          method: 'POST',
          headers: baseHeaders,
          body: JSON.stringify({
            email: studentEmail,
            data: { full_name: studentName, role: 'parent' },
            redirect_to: redirectTo,
          }),
        }
      )

      if (!iOk) {
        const errMsg = ((iData as Record<string, string>)?.msg ?? (iData as Record<string, string>)?.message ?? '').toLowerCase()
        if (iStatus === 429 || errMsg.includes('rate limit') || errMsg.includes('over_email')) {
          anyRateLimited = true
          results.push({ email: studentEmail, status: 'rate_limited' })
        } else {
          results.push({ email: studentEmail, status: 'exists' })
        }
      } else {
        results.push({ email: studentEmail, status: 'sent' })
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        rate_limited: anyRateLimited,
        results,
        warning: anyRateLimited
          ? 'Limite de e-mails atingido para alguns contatos. Use o link de convite para esses.'
          : undefined,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.error(`[invite-student][${step}]`, message)
    return new Response(
      JSON.stringify({ error: `[${step}] ${message}` }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
