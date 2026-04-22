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

    // ── 1. Autenticação ──────────────────────────────────────────
    step = 'auth'
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) throw new Error('Header Authorization ausente')
    const jwt = authHeader.replace('Bearer ', '')
    const payload = decodeJWT(jwt)
    if (!payload?.sub) throw new Error('JWT inválido ou expirado')
    const userId = payload.sub as string

    // ── 2. Ler body ──────────────────────────────────────────────
    step = 'body'
    const rawBody = await req.text()
    if (!rawBody?.trim()) throw new Error('Body vazio')
    let body: Record<string, unknown>
    try { body = JSON.parse(rawBody) }
    catch { throw new Error(`Body inválido: "${rawBody.slice(0, 80)}"`) }

    const { email, full_name, discipline, room, bio, grade_levels, subject_ids, grade_ids } = body as {
      email: string; full_name: string; discipline?: string
      room?: string; bio?: string; grade_levels?: string[]
      subject_ids?: string[]; grade_ids?: string[]
    }
    if (!email || !full_name) throw new Error('email e full_name são obrigatórios')

    // ── 3. Verificar admin ───────────────────────────────────────
    step = 'check_admin'
    const { ok: pOk, status: pStatus, data: pData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${userId}&select=role`,
      { headers: baseHeaders }
    )
    if (!pOk) throw new Error(`REST profiles erro ${pStatus}: ${JSON.stringify(pData).slice(0, 100)}`)
    const adminProfiles = pData as Array<{ role: string }>
    if (!Array.isArray(adminProfiles) || adminProfiles[0]?.role !== 'admin') {
      throw new Error(`Acesso negado (role="${adminProfiles[0]?.role ?? 'nenhum'}")`)
    }

    // ── 4. Salvar convite ────────────────────────────────────────
    step = 'save_invite'
    const { ok: sOk, status: sStatus, data: sData } = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teacher_invites`,
      {
        method: 'POST',
        headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
        body: JSON.stringify({
          email, full_name,
          discipline:   discipline   || null,
          room:         room         || null,
          bio:          bio          || null,
          grade_levels: grade_levels || null,
          subject_ids:  subject_ids  || [],
          grade_ids:    grade_ids    || [],
        }),
      }
    )
    // 409 = convite já existe para este e-mail (ok, continua)
    if (!sOk && sStatus !== 409) {
      throw new Error(`Erro ao salvar convite (${sStatus}): ${JSON.stringify(sData).slice(0, 100)}`)
    }

    // ── 5. Enviar e-mail de convite ──────────────────────────────
    step = 'send_invite'
    const origin     = req.headers.get('origin') || 'http://localhost:5173'
    const redirectTo = `${origin}/reset-password`

    const { ok: iOk, status: iStatus, data: iData } = await fetchJSON(
      `${SUPABASE_URL}/auth/v1/invite`,
      {
        method: 'POST',
        headers: baseHeaders,
        body: JSON.stringify({ email, data: { full_name, role: 'teacher' }, redirect_to: redirectTo }),
      }
    )

    if (!iOk) {
      const errMsg = (
        (iData as Record<string, string>)?.msg ??
        (iData as Record<string, string>)?.message ??
        (iData as Record<string, string>)?.error ?? ''
      ).toLowerCase()

      // ── Usuário já existe no auth ──────────────────────────────
      if (errMsg.includes('already') || errMsg.includes('registered') || errMsg.includes('exists')) {
        step = 'restore_teacher'

        // Busca o profile pelo e-mail
        const { data: existingProfiles } = await fetchJSON(
          `${SUPABASE_URL}/rest/v1/profiles?email=eq.${encodeURIComponent(email)}&select=id,role`,
          { headers: baseHeaders }
        )
        const existingProfile = (existingProfiles as Array<{ id: string; role: string }>)?.[0]

        if (existingProfile) {
          // Verifica se já tem registro na tabela teachers
          const { data: existingTeachers } = await fetchJSON(
            `${SUPABASE_URL}/rest/v1/teachers?profile_id=eq.${existingProfile.id}&select=id`,
            { headers: baseHeaders }
          )
          const teacherExists = (existingTeachers as Array<unknown>)?.length > 0

          if (!teacherExists) {
            // Recria o registro de professor (conta existe, teachers foi apagado)
            const { ok: tOk, data: tData } = await fetchJSON(
              `${SUPABASE_URL}/rest/v1/teachers`,
              {
                method: 'POST',
                headers: { ...baseHeaders, 'Prefer': 'return=representation' },
                body: JSON.stringify({
                  profile_id:   existingProfile.id,
                  discipline:   discipline   || null,
                  room:         room         || null,
                  bio:          bio          || null,
                  grade_levels: grade_levels || null,
                  is_active:    true,
                }),
              }
            )

            if (tOk) {
              // Vincula matérias e turmas se fornecidas
              const newTeacher = (tData as Array<{ id: string }>)?.[0]
              if (newTeacher?.id) {
                if (subject_ids?.length) {
                  await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_subjects`, {
                    method: 'POST',
                    headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
                    body: JSON.stringify(subject_ids.map(sid => ({ teacher_id: newTeacher.id, subject_id: sid }))),
                  })
                }
                if (grade_ids?.length) {
                  await fetchJSON(`${SUPABASE_URL}/rest/v1/teacher_grades`, {
                    method: 'POST',
                    headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
                    body: JSON.stringify(grade_ids.map(gid => ({ teacher_id: newTeacher.id, grade_id: gid }))),
                  })
                }
              }
              // Atualiza role do profile para teacher (garantia)
              await fetchJSON(
                `${SUPABASE_URL}/rest/v1/profiles?id=eq.${existingProfile.id}`,
                {
                  method: 'PATCH',
                  headers: { ...baseHeaders, 'Prefer': 'return=minimal' },
                  body: JSON.stringify({ role: 'teacher', full_name }),
                }
              )
              // Remove o convite pendente (não é mais necessário)
              await fetchJSON(
                `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(email)}`,
                { method: 'DELETE', headers: baseHeaders }
              )
              return new Response(
                JSON.stringify({ success: true, restored: true, message: `Professor ${full_name} reativado com sucesso.` }),
                { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
              )
            }
          } else {
            // Já tem registro ativo — remove o convite duplicado e retorna aviso
            await fetchJSON(
              `${SUPABASE_URL}/rest/v1/teacher_invites?email=eq.${encodeURIComponent(email)}`,
              { method: 'DELETE', headers: baseHeaders }
            )
            return new Response(
              JSON.stringify({ success: true, already_active: true, warning: `${full_name} já está cadastrado e ativo no sistema.` }),
              { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
          }
        }

        return new Response(
          JSON.stringify({ success: true, warning: 'Usuário já cadastrado. O convite foi salvo.' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // ── Rate limit ─────────────────────────────────────────────
      if (iStatus === 429 || errMsg.includes('rate limit') || errMsg.includes('over_email')) {
        return new Response(
          JSON.stringify({
            success: true,
            rate_limited: true,
            warning: `Limite de e-mails atingido. Convite salvo! Use o link de cadastro para ${email}`,
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      throw new Error(`Erro ao enviar e-mail (${iStatus}): ${JSON.stringify(iData).slice(0, 150)}`)
    }

    return new Response(
      JSON.stringify({ success: true, message: `Convite enviado para ${email}` }),
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
