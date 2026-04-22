-- ══════════════════════════════════════════════════════════════
-- MIGRAÇÃO: Turmas, Matérias, Alunos, Responsáveis
-- Cole no SQL Editor do Supabase e execute
-- ══════════════════════════════════════════════════════════════

-- ── 1. Turmas ──────────────────────────────────────────────────
create table if not exists grades (
  id         uuid primary key default gen_random_uuid(),
  name       text not null unique,
  sort_order int  default 0,
  created_at timestamptz default now()
);
alter table grades enable row level security;
drop policy if exists "grades_select" on grades;
drop policy if exists "grades_admin"  on grades;
create policy "grades_select" on grades for select using (true);
create policy "grades_admin"  on grades for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 2. Matérias ────────────────────────────────────────────────
create table if not exists subjects (
  id         uuid primary key default gen_random_uuid(),
  name       text not null unique,
  sort_order int  default 0,
  created_at timestamptz default now()
);
alter table subjects enable row level security;
drop policy if exists "subjects_select" on subjects;
drop policy if exists "subjects_admin"  on subjects;
create policy "subjects_select" on subjects for select using (true);
create policy "subjects_admin"  on subjects for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 3. Professor ↔ Turma ───────────────────────────────────────
create table if not exists teacher_grades (
  teacher_id uuid references teachers(id) on delete cascade,
  grade_id   uuid references grades(id)   on delete cascade,
  primary key (teacher_id, grade_id)
);
alter table teacher_grades enable row level security;
drop policy if exists "teacher_grades_select" on teacher_grades;
drop policy if exists "teacher_grades_admin"  on teacher_grades;
create policy "teacher_grades_select" on teacher_grades for select using (true);
create policy "teacher_grades_admin"  on teacher_grades for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 4. Professor ↔ Matéria ─────────────────────────────────────
create table if not exists teacher_subjects (
  teacher_id uuid references teachers(id)  on delete cascade,
  subject_id uuid references subjects(id)  on delete cascade,
  primary key (teacher_id, subject_id)
);
alter table teacher_subjects enable row level security;
drop policy if exists "teacher_subjects_select" on teacher_subjects;
drop policy if exists "teacher_subjects_admin"  on teacher_subjects;
create policy "teacher_subjects_select" on teacher_subjects for select using (true);
create policy "teacher_subjects_admin"  on teacher_subjects for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 5. Adiciona colunas ao teacher_invites ─────────────────────
alter table teacher_invites
  add column if not exists subject_ids uuid[] default '{}',
  add column if not exists grade_ids   uuid[] default '{}';

-- ── 6. Registros de Alunos (gerenciados pelo admin) ────────────
create table if not exists student_records (
  id                  uuid primary key default gen_random_uuid(),
  full_name           text not null,
  grade_id            uuid references grades(id),
  student_email       text,
  send_student_invite boolean default false,
  created_at          timestamptz default now()
);
alter table student_records enable row level security;
drop policy if exists "student_records_admin"       on student_records;
drop policy if exists "student_records_parent_read" on student_records;
create policy "student_records_admin" on student_records for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');
-- pais/responsáveis leem só o(s) aluno(s) deles (policy referencia parent_student_links criada abaixo)

-- ── 7. Aluno ↔ Matéria ─────────────────────────────────────────
create table if not exists student_record_subjects (
  student_record_id uuid references student_records(id) on delete cascade,
  subject_id        uuid references subjects(id)         on delete cascade,
  primary key (student_record_id, subject_id)
);
alter table student_record_subjects enable row level security;
drop policy if exists "srs_admin" on student_record_subjects;
create policy "srs_admin" on student_record_subjects for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 8. Responsáveis do Aluno ───────────────────────────────────
create table if not exists student_record_responsibles (
  id                uuid primary key default gen_random_uuid(),
  student_record_id uuid references student_records(id) on delete cascade,
  full_name         text not null,
  email             text not null,
  order_num         int  not null check (order_num in (1, 2)),
  invite_sent_at    timestamptz,
  unique (student_record_id, order_num)
);
alter table student_record_responsibles enable row level security;
drop policy if exists "srr_admin" on student_record_responsibles;
create policy "srr_admin" on student_record_responsibles for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 9. Exceções de professor por aluno ────────────────────────
create table if not exists student_record_teacher_overrides (
  id                uuid primary key default gen_random_uuid(),
  student_record_id uuid references student_records(id) on delete cascade,
  teacher_id        uuid references teachers(id)         on delete cascade,
  action            text not null check (action in ('add', 'remove')),
  unique (student_record_id, teacher_id)
);
alter table student_record_teacher_overrides enable row level security;
drop policy if exists "srto_admin" on student_record_teacher_overrides;
create policy "srto_admin" on student_record_teacher_overrides for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- ── 10. Vínculo Responsável ↔ Aluno ───────────────────────────
create table if not exists parent_student_links (
  profile_id        uuid references profiles(id)        on delete cascade,
  student_record_id uuid references student_records(id) on delete cascade,
  primary key (profile_id, student_record_id)
);
alter table parent_student_links enable row level security;
drop policy if exists "psl_admin"  on parent_student_links;
drop policy if exists "psl_parent" on parent_student_links;
create policy "psl_admin"  on parent_student_links for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');
create policy "psl_parent" on parent_student_links for select
  using (profile_id = auth.uid());

-- ── 11. Convites de Alunos/Responsáveis ───────────────────────
create table if not exists student_invites (
  id                uuid primary key default gen_random_uuid(),
  email             text not null unique,
  full_name         text not null,
  student_record_id uuid references student_records(id) on delete cascade,
  invite_type       text not null check (invite_type in ('responsible', 'student')),
  created_at        timestamptz default now()
);
alter table student_invites enable row level security;
drop policy if exists "student_invites_admin" on student_invites;
create policy "student_invites_admin" on student_invites for all
  using (get_my_role() = 'admin') with check (get_my_role() = 'admin');

-- Agora adiciona policy de leitura para student_records para responsáveis
create policy "student_records_parent_read" on student_records for select
  using (
    exists (
      select 1 from parent_student_links l
      where l.profile_id = auth.uid()
        and l.student_record_id = student_records.id
    )
  );

create policy "srs_parent" on student_record_subjects for select
  using (
    exists (
      select 1 from parent_student_links l
      where l.profile_id = auth.uid()
        and l.student_record_id = student_record_subjects.student_record_id
    )
  );

-- ── 12. Atualiza trigger handle_new_user ──────────────────────
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
declare
  v_role           text := 'parent';
  v_name           text;
  v_teacher_invite teacher_invites%rowtype;
  v_student_invite student_invites%rowtype;
  v_new_teacher_id uuid;
begin
  v_name := coalesce(
    new.raw_user_meta_data->>'full_name',
    split_part(new.email, '@', 1)
  );

  -- ── Convite de professor ─────────────────────────────────────
  select * into v_teacher_invite from teacher_invites where email = new.email;

  if v_teacher_invite.id is not null then
    v_role := 'teacher';
    v_name := coalesce(new.raw_user_meta_data->>'full_name', v_teacher_invite.full_name, v_name);

    insert into profiles (id, email, full_name, role)
    values (new.id, new.email, v_name, v_role)
    on conflict (id) do nothing;

    insert into teachers (profile_id, discipline, room, bio, grade_levels, is_active)
    values (new.id, v_teacher_invite.discipline, v_teacher_invite.room,
            v_teacher_invite.bio, v_teacher_invite.grade_levels, true)
    on conflict do nothing
    returning id into v_new_teacher_id;

    -- Vincula matérias
    if v_teacher_invite.subject_ids is not null
       and array_length(v_teacher_invite.subject_ids, 1) > 0 then
      insert into teacher_subjects (teacher_id, subject_id)
      select v_new_teacher_id, unnest(v_teacher_invite.subject_ids)
      on conflict do nothing;
    end if;

    -- Vincula turmas
    if v_teacher_invite.grade_ids is not null
       and array_length(v_teacher_invite.grade_ids, 1) > 0 then
      insert into teacher_grades (teacher_id, grade_id)
      select v_new_teacher_id, unnest(v_teacher_invite.grade_ids)
      on conflict do nothing;
    end if;

    delete from teacher_invites where id = v_teacher_invite.id;
    return new;
  end if;

  -- ── Convite de responsável/aluno ─────────────────────────────
  select * into v_student_invite from student_invites where email = new.email;

  if v_student_invite.id is not null then
    v_role := 'parent';
    v_name := coalesce(new.raw_user_meta_data->>'full_name', v_student_invite.full_name, v_name);

    insert into profiles (id, email, full_name, role)
    values (new.id, new.email, v_name, v_role)
    on conflict (id) do nothing;

    insert into parent_student_links (profile_id, student_record_id)
    values (new.id, v_student_invite.student_record_id)
    on conflict do nothing;

    delete from student_invites where id = v_student_invite.id;
    return new;
  end if;

  -- ── Cadastro comum (pai/responsável sem convite) ─────────────
  insert into profiles (id, email, full_name, role)
  values (new.id, new.email, v_name, v_role)
  on conflict (id) do nothing;

  return new;
exception when others then
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
