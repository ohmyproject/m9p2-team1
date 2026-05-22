create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create table public."JK_job" (
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

create table public.user_roadmaps (
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

create table public.chat_threads (
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

create table public.chat_sessions (
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

create table public.chat_messages (
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






create index user_roadmaps_user_id_created_at_idx
  on public.user_roadmaps using btree (user_id, created_at desc);

create index chat_threads_user_id_idx
  on public.chat_threads using btree (user_id);

create index chat_threads_user_job_idx
  on public.chat_threads using btree (user_id, job_name);

create index chat_sessions_thread_id_idx
  on public.chat_sessions using btree (thread_id);

create index chat_sessions_roadmap_id_idx
  on public.chat_sessions using btree (roadmap_id);

create index chat_messages_thread_created_idx
  on public.chat_messages using btree (thread_id, created_at);

create index chat_messages_session_created_idx
  on public.chat_messages using btree (session_id, created_at);