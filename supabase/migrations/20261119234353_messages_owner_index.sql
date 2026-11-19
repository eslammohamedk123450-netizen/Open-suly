-- Cover the composite message ownership foreign key.
create index messages_conversation_owner_idx on public.messages (conversation_id, user_id);
