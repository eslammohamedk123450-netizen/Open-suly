-- Enforce one assistant response per user message, including concurrent retries.
create unique index messages_one_assistant_reply_per_user_message_idx
  on public.messages (user_id, (metadata ->> 'in_reply_to'))
  where role = 'assistant' and metadata ? 'in_reply_to';
