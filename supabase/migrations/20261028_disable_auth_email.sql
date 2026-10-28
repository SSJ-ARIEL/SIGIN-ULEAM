-- Send Email hook: acknowledge without delivering or retaining email content.
-- Enable with hook_send_email_uri = pg-functions://postgres/public/sigin_suppress_auth_email.
begin;
create or replace function public.sigin_suppress_auth_email(event jsonb)
returns jsonb language sql set search_path = '' as $$ select '{}'::jsonb $$;
revoke all on function public.sigin_suppress_auth_email(jsonb) from public, anon, authenticated;
grant execute on function public.sigin_suppress_auth_email(jsonb) to supabase_auth_admin;
commit;
