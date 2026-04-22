-- ══════════════════════════════════════════════════════════════
-- MIGRAÇÃO: Sistema de convites para professores
-- Cole no SQL Editor do Supabase e execute
-- ══════════════════════════════════════════════════════════════

-- 1. Tabela de convites (sem FK para auth.users — professor ainda não existe)
create table if not exists teacher_invites (
  id           uuid primary key default uuid_generate_v4(),
  email        text not null unique,
  full_name    text not null,
  discipline   text not null,
  room         text,
  bio          text,
  grade_levels text[],
  created_at   timestamptz default now()
);

-- RLS na tabela de convites
alter table teacher_invites enable row level security;

create policy "Admin gerencia convites" on teacher_invites
  for all using (
    exists (select 1 from profiles where id = auth.uid() and role = 'admin')
  );

-- 2. Recria o trigger para checar convites de professor ao registrar
create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_invite  teacher_invites%rowtype;
  v_role    text;
  v_name    text;
begin
  -- Verifica se o e-mail tem um convite de professor pendente
  select * into v_invite from teacher_invites where email = new.email;

  if v_invite.id is not null then
    v_role := 'teacher';
    v_name := v_invite.full_name;
  else
    v_role := coalesce(new.raw_user_meta_data->>'role', 'parent');
    v_name := coalesce(new.raw_user_meta_data->>'full_name', new.email);
  end if;

  -- Cria o profile
  insert into profiles (id, role, full_name, email)
  values (new.id, v_role, v_name, new.email)
  on conflict (id) do nothing;

  -- Se for professor convidado, cria o registro de teacher automaticamente
  if v_invite.id is not null then
    insert into teachers (profile_id, discipline, room, bio, grade_levels)
    values (new.id, v_invite.discipline, v_invite.room, v_invite.bio, v_invite.grade_levels)
    on conflict do nothing;

    -- Remove o convite usado
    delete from teacher_invites where id = v_invite.id;
  end if;

  return new;
exception when others then
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
