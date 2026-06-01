alter table public.app_tx_history enable row level security;

alter table public.app_tx_history
add column if not exists user_id text not null default '';

drop policy if exists "Users can only access their own transactions" on public.app_tx_history;

create policy "Users can only access their own transactions"
on public.app_tx_history
for select
using (auth.uid()::text = user_id);
