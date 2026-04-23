import { corsHeaders } from '../_shared/cors.ts'

async function fetchJSON(url: string, headers: Record<string, string>) {
  const res = await fetch(url, { headers })
  const text = (await res.text()).trim()
  if (!text) return []
  try { return JSON.parse(text) } catch { return [] }
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!
  const SERVICE_KEY  = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  const h = { 'Authorization': `Bearer ${SERVICE_KEY}`, 'apikey': SERVICE_KEY }

  try {
    const { event_day_id, user_id } = await req.json()
    if (!event_day_id) throw new Error('event_day_id obrigatório')

    // Professores ativos com nome do perfil
    const teachers = await fetchJSON(
      `${SUPABASE_URL}/rest/v1/teachers?is_active=eq.true&select=id,discipline,room,profile:profiles(full_name)&order=discipline`,
      h
    )

    const teacherIds = teachers.map((t: Record<string, unknown>) => t.id).join(',')

    // Slots do dia para esses professores
    const slots = teacherIds ? await fetchJSON(
      `${SUPABASE_URL}/rest/v1/time_slots?event_day_id=eq.${event_day_id}&teacher_id=in.(${teacherIds})&select=id,teacher_id,start_time,end_time&order=start_time`,
      h
    ) : []

    const slotIds = slots.map((s: Record<string, unknown>) => s.id).join(',')

    // Bookings desses slots
    const bookings = slotIds ? await fetchJSON(
      `${SUPABASE_URL}/rest/v1/bookings?time_slot_id=in.(${slotIds})&select=id,time_slot_id,parent_id`,
      h
    ) : []

    return new Response(
      JSON.stringify({ teachers, slots, bookings }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return new Response(
      JSON.stringify({ error: msg }),
      { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
