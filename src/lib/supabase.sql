-- ============================================================
-- AGENDA DE CONFERÊNCIAS — PAN AMERICAN
-- Cole este SQL no Supabase SQL Editor e execute
-- ============================================================

-- ── Extensões ───────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ── Limpa tabelas anteriores (ordem importa por FK) ─────────
drop table if exists bookings cascade;
drop table if exists time_slots cascade;
drop table if exists event_days cascade;
drop table if exists conference_events cascade;
drop table if exists students cascade;
drop table if exists teachers cascade;
drop table if exists profiles cascade;

-- ── 1. Profiles (todos os usuários) ─────────────────────────
create table profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  role        text not null check (role in ('admin','teacher','parent')),
  full_name   text not null,
  email       text not null unique,
  avatar_url  text,
  phone       text,
  created_at  timestamptz default now()
);

-- ── 2. Teachers (detalhes do professor) ─────────────────────
create table teachers (
  id           uuid primary key default uuid_generate_v4(),
  profile_id   uuid references profiles(id) on delete cascade,
  discipline   text not null,
  room         text,
  bio          text,
  grade_levels text[],          -- ex: ['6th','7th','8th']
  is_active    boolean default true,
  created_at   timestamptz default now()
);

-- ── 3. Students (filhos/alunos cadastrados pelos pais) ───────
create table students (
  id         uuid primary key default uuid_generate_v4(),
  parent_id  uuid references profiles(id) on delete cascade,
  full_name  text not null,
  grade      text,
  created_at timestamptz default now()
);

-- ── 4. Conference Events ─────────────────────────────────────
create table conference_events (
  id          uuid primary key default uuid_generate_v4(),
  name        text not null,
  description text,
  is_active   boolean default false,
  created_by  uuid references profiles(id),
  created_at  timestamptz default now()
);

-- ── 5. Event Days (cada dia da conferência) ─────────────────
create table event_days (
  id               uuid primary key default uuid_generate_v4(),
  event_id         uuid references conference_events(id) on delete cascade,
  date             date not null,
  slot_start_time  time not null,   -- ex: '18:00'
  slot_end_time    time not null,   -- ex: '22:00'
  interval_minutes int  not null default 10,
  created_at       timestamptz default now()
);

-- ── 6. Time Slots (horários gerados por professor/dia) ────────
create table time_slots (
  id           uuid primary key default uuid_generate_v4(),
  event_day_id uuid references event_days(id) on delete cascade,
  teacher_id   uuid references teachers(id) on delete cascade,
  start_time   time not null,
  end_time     time not null,
  is_available boolean default true,
  created_at   timestamptz default now(),
  unique(event_day_id, teacher_id, start_time)
);

-- ── 7. Bookings ───────────────────────────────────────────────
create table bookings (
  id              uuid primary key default uuid_generate_v4(),
  time_slot_id    uuid references time_slots(id) on delete cascade,
  student_id      uuid references students(id) on delete cascade,
  parent_id       uuid references profiles(id) on delete cascade,
  google_event_id text,
  notes           text,
  created_at      timestamptz default now(),
  unique(time_slot_id)   -- cada slot só pode ter 1 reserva
);

-- ══════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY
-- ══════════════════════════════════════════════════════════════
alter table profiles          enable row level security;
alter table teachers          enable row level security;
alter table students          enable row level security;
alter table conference_events enable row level security;
alter table event_days        enable row level security;
alter table time_slots        enable row level security;
alter table bookings          enable row level security;

-- helpers
create or replace function get_my_role()
returns text language sql security definer
as $$ select role from profiles where id = auth.uid() $$;

-- ── profiles ─────────────────────────────────────────────────
create policy "Leitura própria" on profiles
  for select using (id = auth.uid());

create policy "Admin lê todos" on profiles
  for select using (get_my_role() = 'admin');

create policy "Admin insere" on profiles
  for insert with check (get_my_role() = 'admin');

create policy "Usuário edita próprio" on profiles
  for update using (id = auth.uid());

-- ── teachers ─────────────────────────────────────────────────
create policy "Todos veem professores ativos" on teachers
  for select using (is_active = true);

create policy "Admin gerencia teachers" on teachers
  for all using (get_my_role() = 'admin');

create policy "Professor edita próprio" on teachers
  for update using (profile_id = auth.uid());

-- ── students ─────────────────────────────────────────────────
create policy "Pai vê/gerencia filhos" on students
  for all using (parent_id = auth.uid());

create policy "Admin vê todos estudantes" on students
  for select using (get_my_role() = 'admin');

create policy "Teacher vê estudantes com booking" on students
  for select using (
    get_my_role() = 'teacher' and
    exists (
      select 1 from bookings b
      join time_slots ts on ts.id = b.time_slot_id
      join teachers t on t.id = ts.teacher_id
      where b.student_id = students.id and t.profile_id = auth.uid()
    )
  );

-- ── conference_events ─────────────────────────────────────────
create policy "Todos veem eventos ativos" on conference_events
  for select using (is_active = true);

create policy "Admin gerencia eventos" on conference_events
  for all using (get_my_role() = 'admin');

-- ── event_days ───────────────────────────────────────────────
create policy "Todos veem event_days" on event_days
  for select using (true);

create policy "Admin gerencia event_days" on event_days
  for all using (get_my_role() = 'admin');

-- ── time_slots ───────────────────────────────────────────────
create policy "Todos veem time_slots" on time_slots
  for select using (true);

create policy "Admin gerencia slots" on time_slots
  for all using (get_my_role() = 'admin');

-- ── bookings ─────────────────────────────────────────────────
create policy "Pai vê próprios bookings" on bookings
  for select using (parent_id = auth.uid());

create policy "Pai insere booking" on bookings
  for insert with check (parent_id = auth.uid());

create policy "Pai cancela próprio" on bookings
  for delete using (parent_id = auth.uid());

create policy "Teacher vê bookings do slot dele" on bookings
  for select using (
    get_my_role() = 'teacher' and
    exists (
      select 1 from time_slots ts
      join teachers t on t.id = ts.teacher_id
      where ts.id = bookings.time_slot_id and t.profile_id = auth.uid()
    )
  );

create policy "Admin vê todos bookings" on bookings
  for select using (get_my_role() = 'admin');

-- ══════════════════════════════════════════════════════════════
-- FUNÇÃO: Criar profile automático ao registrar usuário
-- ══════════════════════════════════════════════════════════════
create or replace function handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into profiles (id, role, full_name, email)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'role', 'parent'),
    coalesce(new.raw_user_meta_data->>'full_name', new.email),
    new.email
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ══════════════════════════════════════════════════════════════
-- FUNÇÃO: Gerar time_slots automaticamente para um event_day
-- ══════════════════════════════════════════════════════════════
create or replace function generate_slots_for_day(p_event_day_id uuid)
returns void language plpgsql as $$
declare
  v_day         event_days%rowtype;
  v_teacher     teachers%rowtype;
  v_current     time;
  v_end_slot    time;
begin
  select * into v_day from event_days where id = p_event_day_id;

  for v_teacher in select * from teachers where is_active = true loop
    v_current := v_day.slot_start_time;
    while v_current < v_day.slot_end_time loop
      v_end_slot := v_current + (v_day.interval_minutes || ' minutes')::interval;
      insert into time_slots (event_day_id, teacher_id, start_time, end_time)
      values (p_event_day_id, v_teacher.id, v_current, v_end_slot)
      on conflict (event_day_id, teacher_id, start_time) do nothing;
      v_current := v_end_slot;
    end loop;
  end loop;
end;
$$;
