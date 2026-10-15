-- Objets isolés ; aucune table EdgeScope existante n'est modifiée.
create table public.cv_push_config (
  id boolean primary key default true check (id),
  value jsonb not null
);
create table public.cv_push_devices (
  id uuid primary key,
  token_hash text not null,
  endpoint_hash text not null unique,
  subscription jsonb not null,
  strategies text[] not null,
  created_at timestamptz not null default now(),
  since_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  test_at timestamptz,
  enabled boolean not null default true
);
create table public.cv_push_deliveries (
  device_id uuid references public.cv_push_devices(id) on delete cascade,
  alert_id text not null,
  claimed_at timestamptz not null default now(),
  sent_at timestamptz,
  attempts integer not null default 1,
  primary key(device_id, alert_id)
);
alter table public.cv_push_config enable row level security;
alter table public.cv_push_devices enable row level security;
alter table public.cv_push_deliveries enable row level security;
revoke all on public.cv_push_config, public.cv_push_devices, public.cv_push_deliveries from public, anon, authenticated;
grant all on public.cv_push_config, public.cv_push_devices, public.cv_push_deliveries to service_role;

create function public.cv_push_claim(p_device uuid, p_alert text)
returns boolean language sql security invoker set search_path = '' as $$
  with claim as (
    insert into public.cv_push_deliveries(device_id,alert_id) values(p_device,p_alert)
    on conflict(device_id,alert_id) do update
      set claimed_at=now(), attempts=cv_push_deliveries.attempts+1
      where cv_push_deliveries.sent_at is null
        and cv_push_deliveries.claimed_at < now()-interval '2 minutes'
        and cv_push_deliveries.attempts < 3
    returning 1
  ) select exists(select 1 from claim);
$$;
revoke all on function public.cv_push_claim(uuid,text) from public, anon, authenticated;
grant execute on function public.cv_push_claim(uuid,text) to service_role;

create function public.cv_push_register(p_id uuid, p_token text, p_endpoint text,
  p_subscription jsonb, p_strategies text[])
returns boolean language plpgsql security invoker set search_path = '' as $$
declare old_token text;
begin
  -- Sérialise la limite globale et les collisions d'identité.
  perform pg_advisory_xact_lock(1404917041);
  select token_hash into old_token from public.cv_push_devices where id=p_id;
  if found and old_token<>p_token then return false; end if;
  if old_token is null and (select count(*) from public.cv_push_devices)>=20 then return false; end if;
  insert into public.cv_push_devices(id,token_hash,endpoint_hash,subscription,strategies)
    values(p_id,p_token,p_endpoint,p_subscription,p_strategies)
    on conflict(id) do update set endpoint_hash=p_endpoint, subscription=p_subscription,
      strategies=p_strategies, enabled=true, since_at=now(), updated_at=now();
  return true;
end;
$$;
revoke all on function public.cv_push_register(uuid,text,text,jsonb,text[]) from public, anon, authenticated;
grant execute on function public.cv_push_register(uuid,text,text,jsonb,text[]) to service_role;
