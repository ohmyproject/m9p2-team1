-- 노비 Job아라 Supabase schema setup

-- 작성 목적:
--   1. README의 "Supabase 준비 사항"에 적힌 테이블/확장/RPC/RLS를 한 번에 재생성
--   2. 현재 프로젝트 코드(src/main.py)가 기대하는 테이블명, 컬럼명, 함수명을 보존
--
-- 주의:
--   - 이 파일은 스키마 생성용입니다. JK_job의 실제 직무 데이터와 embedding 값은 별도로 적재해야 합니다.
--   - 이미 운영 중인 DB에 실행하기 전에는 반드시 백업하거나 SQL Editor에서 한 구문씩 검토하세요.
--   - auth.users 테이블은 Supabase Auth가 제공하므로 여기에서 직접 생성하지 않습니다.

-- ---------------------------------------------------------------------------
-- 1. Extensions
-- ---------------------------------------------------------------------------
-- gen_random_uuid() 기본값을 사용하기 위한 확장입니다.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

-- JK_job.embedding 컬럼과 match_jobs RPC에서 사용하는 pgvector 확장입니다.
-- 현재 DB 구조는 vector(1536) 타입을 직접 사용합니다.
create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- 2. Public job catalog
-- ---------------------------------------------------------------------------
-- JK_job:
--   - 전체 직무 카탈로그입니다.
--   - RIASEC 점수, 전공 요구 여부, 직무 상세 설명, RAG 검색용 embedding을 저장합니다.
--   - 사용자가 직접 소유하는 데이터가 아니므로 anon/authenticated 모두 SELECT만 허용합니다.
create table if not exists public."JK_job" (
  id bigint not null,
  "JK_L_category" text,
  "JK_M_category" text,
  top3 text,
  realistic_score double precision,
  investigative_score double precision,
  artistic_score double precision,
  social_score double precision,
  enterprising_score double precision,
  conventional_score double precision,
  major_required text,
  job_information text,
  embedding vector(1536),
  constraint "JK_job_pkey" primary key (id)
);

comment on table public."JK_job" is 'Public job catalog migrated from Cloud SQL JK_job.';
comment on column public."JK_job"."JK_L_category" is '직무 대분류';
comment on column public."JK_job"."JK_M_category" is '직무 중분류 또는 직무명';
comment on column public."JK_job".top3 is '직무와 관련된 상위 RIASEC 코드';
comment on column public."JK_job".major_required is '전공 요구 여부 또는 전공 관련 설명';
comment on column public."JK_job".job_information is '직무 상세 설명';
comment on column public."JK_job".embedding is 'OpenAI embedding 기반 RAG 검색 벡터, text-embedding-3-small 기준 1536차원';

-- ---------------------------------------------------------------------------
-- 3. User roadmap history
-- ---------------------------------------------------------------------------
-- user_roadmaps:
--   - 사용자가 생성한 AI 로드맵 기록을 저장합니다.
--   - user_id는 Supabase Auth의 auth.users.id를 참조합니다.
--   - riasec_scores는 PDF에서 추출한 점수 또는 프론트에서 전달된 점수를 JSON으로 저장합니다.
create table if not exists public.user_roadmaps (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  job_name text not null,
  riasec_scores jsonb,
  roadmap_text text not null,
  created_at timestamp with time zone not null default now(),
  job_information text,
  constraint user_roadmaps_pkey primary key (id),
  constraint user_roadmaps_user_id_fkey
    foreign key (user_id) references auth.users(id) on delete cascade
);

comment on table public.user_roadmaps is 'Stores AI roadmap results for each authenticated user.';
comment on column public.user_roadmaps.user_id is '로드맵을 생성한 Supabase Auth 사용자 ID';
comment on column public.user_roadmaps.job_name is '로드맵 대상 직무명';
comment on column public.user_roadmaps.riasec_scores is '사용자의 RIASEC 점수 JSON';
comment on column public.user_roadmaps.roadmap_text is 'OpenAI가 생성한 로드맵 본문';
comment on column public.user_roadmaps.job_information is '로드맵 생성 시 참고한 직무 상세 정보';

create index if not exists user_roadmaps_user_id_created_at_idx
  on public.user_roadmaps using btree (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- 4. Chat memory tables
-- ---------------------------------------------------------------------------
-- chat_threads:
--   - 사용자 + 직무 단위의 상담 스레드입니다.
--   - 현재 코드는 scope='job'만 사용합니다.
--   - user_id, job_name, scope 조합을 unique로 두어 같은 직무 상담 스레드를 재사용합니다.
create table if not exists public.chat_threads (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  job_name text not null,
  scope text not null default 'job'::text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint chat_threads_pkey primary key (id),
  constraint chat_threads_scope_check check (scope = 'job'::text),
  constraint chat_threads_user_id_fkey
    foreign key (user_id) references auth.users(id) on delete cascade,
  constraint chat_threads_user_job_unique unique (user_id, job_name, scope)
);

comment on table public.chat_threads is '사용자와 직무 조합별 RAG 챗봇 상담 스레드';
comment on column public.chat_threads.scope is '현재 프로젝트에서는 job 고정';

create index if not exists chat_threads_user_id_idx
  on public.chat_threads using btree (user_id);

create index if not exists chat_threads_user_job_idx
  on public.chat_threads using btree (user_id, job_name);

-- chat_sessions:
--   - 특정 로드맵과 특정 채팅 스레드를 연결하는 세션입니다.
--   - 같은 thread_id + roadmap_id 조합은 하나만 유지합니다.
create table if not exists public.chat_sessions (
  id uuid not null default gen_random_uuid(),
  thread_id uuid not null,
  roadmap_id uuid not null,
  roadmap_text text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint chat_sessions_pkey primary key (id),
  constraint chat_sessions_thread_id_fkey
    foreign key (thread_id) references public.chat_threads(id) on delete cascade,
  constraint chat_sessions_roadmap_id_fkey
    foreign key (roadmap_id) references public.user_roadmaps(id) on delete cascade,
  constraint chat_sessions_thread_roadmap_unique unique (thread_id, roadmap_id)
);

comment on table public.chat_sessions is '로드맵별 RAG 챗봇 상담 세션';
comment on column public.chat_sessions.roadmap_text is '세션 생성 시점의 로드맵 본문 스냅샷';

create index if not exists chat_sessions_thread_id_idx
  on public.chat_sessions using btree (thread_id);

create index if not exists chat_sessions_roadmap_id_idx
  on public.chat_sessions using btree (roadmap_id);

-- chat_messages:
--   - 사용자 질문과 AI 답변을 저장합니다.
--   - role은 user, assistant, system 중 하나만 허용합니다.
--   - citations는 추후 출처/근거를 담을 수 있도록 jsonb 배열 기본값을 둡니다.
create table if not exists public.chat_messages (
  id uuid not null default gen_random_uuid(),
  thread_id uuid not null,
  session_id uuid not null,
  role text not null,
  content text not null,
  citations jsonb not null default '[]'::jsonb,
  created_at timestamp with time zone not null default now(),
  constraint chat_messages_pkey primary key (id),
  constraint chat_messages_role_check
    check (role = any (array['user'::text, 'assistant'::text, 'system'::text])),
  constraint chat_messages_thread_id_fkey
    foreign key (thread_id) references public.chat_threads(id) on delete cascade,
  constraint chat_messages_session_id_fk
    foreign key (session_id) references public.chat_sessions(id) on delete cascade
);

comment on table public.chat_messages is 'RAG 챗봇의 사용자/AI 대화 메시지';
comment on column public.chat_messages.citations is '답변 출처 또는 검색 근거를 담기 위한 JSON 배열';

create index if not exists chat_messages_thread_created_idx
  on public.chat_messages using btree (thread_id, created_at);

create index if not exists chat_messages_session_created_idx
  on public.chat_messages using btree (session_id, created_at);

-- ---------------------------------------------------------------------------
-- 5. RAG search RPC
-- ---------------------------------------------------------------------------
-- match_jobs:
--   - src/main.py의 custom_search_jobs()에서 호출하는 RPC 함수입니다.
--   - query_embedding과 JK_job.embedding을 cosine distance(<=>)로 비교합니다.
--   - similarity가 match_threshold보다 큰 직무를 match_count개까지 반환합니다.
create or replace function public.match_jobs(
  query_embedding vector,
  match_threshold double precision,
  match_count integer
)
returns table (
  id bigint,
  "JK_M_category" text,
  job_information text,
  similarity double precision
)
language sql
stable
as $function$
  select
    id,
    "JK_M_category",
    job_information,
    1 - (embedding <=> query_embedding) as similarity
  from public."JK_job"
  where 1 - (embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
$function$;

comment on function public.match_jobs(vector, double precision, integer)
  is 'RAG 챗봇용 직무 벡터 유사도 검색 RPC';

-- ---------------------------------------------------------------------------
-- 6. Grants
-- ---------------------------------------------------------------------------
-- Supabase Data API(PostgREST)에서 각 role이 테이블과 RPC를 사용할 수 있도록 권한을 부여합니다.
-- 실제 행 접근 범위는 아래 RLS 정책이 다시 제한합니다.
grant usage on schema public to anon, authenticated, service_role;

grant select on table public."JK_job" to anon, authenticated;
grant select, insert, update, delete on table public.user_roadmaps to authenticated;
grant select, insert, update, delete on table public.chat_threads to authenticated;
grant select, insert, update, delete on table public.chat_sessions to authenticated;
grant select, insert, update, delete on table public.chat_messages to authenticated;

grant execute on function public.match_jobs(vector, double precision, integer)
  to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 7. Row Level Security
-- ---------------------------------------------------------------------------
-- public 스키마는 Data API에 노출될 수 있으므로 모든 테이블에 RLS를 켭니다.
alter table public."JK_job" enable row level security;
alter table public.user_roadmaps enable row level security;
alter table public.chat_threads enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

-- 정책을 재실행할 수 있도록 기존 정책을 먼저 제거합니다.
drop policy if exists "Public job catalog is readable" on public."JK_job";

drop policy if exists "Users can view their own roadmaps" on public.user_roadmaps;
drop policy if exists "Users can create their own roadmaps" on public.user_roadmaps;
drop policy if exists "Users can update their own roadmaps" on public.user_roadmaps;
drop policy if exists "Users can delete their own roadmaps" on public.user_roadmaps;

drop policy if exists chat_threads_select_own on public.chat_threads;
drop policy if exists chat_threads_insert_own on public.chat_threads;
drop policy if exists chat_threads_update_own on public.chat_threads;
drop policy if exists chat_threads_delete_own on public.chat_threads;

drop policy if exists chat_sessions_select_own on public.chat_sessions;
drop policy if exists chat_sessions_insert_own on public.chat_sessions;
drop policy if exists chat_sessions_update_own on public.chat_sessions;
drop policy if exists chat_sessions_delete_own on public.chat_sessions;

drop policy if exists chat_messages_select_own on public.chat_messages;
drop policy if exists chat_messages_insert_own on public.chat_messages;
drop policy if exists chat_messages_update_own on public.chat_messages;
drop policy if exists chat_messages_delete_own on public.chat_messages;

-- JK_job은 공개 직무 카탈로그이므로 읽기만 허용합니다.
create policy "Public job catalog is readable"
on public."JK_job"
for select
to anon, authenticated
using (true);

-- user_roadmaps는 본인 user_id와 auth.uid()가 일치하는 행만 접근합니다.
create policy "Users can view their own roadmaps"
on public.user_roadmaps
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can create their own roadmaps"
on public.user_roadmaps
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users can update their own roadmaps"
on public.user_roadmaps
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users can delete their own roadmaps"
on public.user_roadmaps
for delete
to authenticated
using ((select auth.uid()) = user_id);

-- chat_threads는 본인 스레드만 접근합니다.
create policy chat_threads_select_own
on public.chat_threads
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy chat_threads_insert_own
on public.chat_threads
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy chat_threads_update_own
on public.chat_threads
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy chat_threads_delete_own
on public.chat_threads
for delete
to authenticated
using ((select auth.uid()) = user_id);

-- chat_sessions는 연결된 thread와 roadmap이 모두 현재 사용자 소유일 때만 접근합니다.
create policy chat_sessions_select_own
on public.chat_sessions
for select
to authenticated
using (
  exists (
    select 1
    from public.chat_threads t
    join public.user_roadmaps r on r.id = chat_sessions.roadmap_id
    where t.id = chat_sessions.thread_id
      and t.user_id = (select auth.uid())
      and r.user_id = (select auth.uid())
  )
);

create policy chat_sessions_insert_own
on public.chat_sessions
for insert
to authenticated
with check (
  exists (
    select 1
    from public.chat_threads t
    join public.user_roadmaps r on r.id = chat_sessions.roadmap_id
    where t.id = chat_sessions.thread_id
      and t.user_id = (select auth.uid())
      and r.user_id = (select auth.uid())
  )
);

create policy chat_sessions_update_own
on public.chat_sessions
for update
to authenticated
using (
  exists (
    select 1
    from public.chat_threads t
    join public.user_roadmaps r on r.id = chat_sessions.roadmap_id
    where t.id = chat_sessions.thread_id
      and t.user_id = (select auth.uid())
      and r.user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1
    from public.chat_threads t
    join public.user_roadmaps r on r.id = chat_sessions.roadmap_id
    where t.id = chat_sessions.thread_id
      and t.user_id = (select auth.uid())
      and r.user_id = (select auth.uid())
  )
);

create policy chat_sessions_delete_own
on public.chat_sessions
for delete
to authenticated
using (
  exists (
    select 1
    from public.chat_threads t
    join public.user_roadmaps r on r.id = chat_sessions.roadmap_id
    where t.id = chat_sessions.thread_id
      and t.user_id = (select auth.uid())
      and r.user_id = (select auth.uid())
  )
);

-- chat_messages는 연결된 session/thread가 현재 사용자 소유일 때만 접근합니다.
create policy chat_messages_select_own
on public.chat_messages
for select
to authenticated
using (
  exists (
    select 1
    from public.chat_sessions s
    join public.chat_threads t on t.id = s.thread_id
    where s.id = chat_messages.session_id
      and s.thread_id = chat_messages.thread_id
      and t.user_id = (select auth.uid())
  )
);

create policy chat_messages_insert_own
on public.chat_messages
for insert
to authenticated
with check (
  exists (
    select 1
    from public.chat_sessions s
    join public.chat_threads t on t.id = s.thread_id
    where s.id = chat_messages.session_id
      and s.thread_id = chat_messages.thread_id
      and t.user_id = (select auth.uid())
  )
);

create policy chat_messages_update_own
on public.chat_messages
for update
to authenticated
using (
  exists (
    select 1
    from public.chat_sessions s
    join public.chat_threads t on t.id = s.thread_id
    where s.id = chat_messages.session_id
      and s.thread_id = chat_messages.thread_id
      and t.user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1
    from public.chat_sessions s
    join public.chat_threads t on t.id = s.thread_id
    where s.id = chat_messages.session_id
      and s.thread_id = chat_messages.thread_id
      and t.user_id = (select auth.uid())
  )
);

create policy chat_messages_delete_own
on public.chat_messages
for delete
to authenticated
using (
  exists (
    select 1
    from public.chat_sessions s
    join public.chat_threads t on t.id = s.thread_id
    where s.id = chat_messages.session_id
      and s.thread_id = chat_messages.thread_id
      and t.user_id = (select auth.uid())
  )
);
