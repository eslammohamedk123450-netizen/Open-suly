-- Store the centrally configured AI provider as one encrypted Supabase Vault secret.
-- Only the server-side service_role may call these narrow RPCs; the Expo client
-- never receives a database function that can read or write the secret.

CREATE OR REPLACE FUNCTION public.suly_ai_provider_config_get()
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
  SELECT ds.decrypted_secret::jsonb
  FROM vault.decrypted_secrets AS ds
  WHERE ds.name = 'suly_ai_provider_config'
  ORDER BY ds.updated_at DESC
  LIMIT 1;
$function$;

CREATE OR REPLACE FUNCTION public.suly_ai_provider_config_set(p_config jsonb)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  v_secret_id uuid;
BEGIN
  IF pg_catalog.jsonb_typeof(p_config) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'AI provider config must be a JSON object';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('suly_ai_provider_config', 0)
  );

  SELECT s.id
  INTO v_secret_id
  FROM vault.secrets AS s
  WHERE s.name = 'suly_ai_provider_config'
  ORDER BY s.created_at
  LIMIT 1
  FOR UPDATE;

  IF v_secret_id IS NULL THEN
    PERFORM vault.create_secret(
      p_config::text,
      'suly_ai_provider_config',
      'Owner-managed SULY AI provider configuration'
    );
  ELSE
    PERFORM vault.update_secret(
      v_secret_id,
      p_config::text,
      'suly_ai_provider_config',
      'Owner-managed SULY AI provider configuration'
    );
  END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.suly_ai_provider_config_clear()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
  DELETE FROM vault.secrets
  WHERE name = 'suly_ai_provider_config';
END;
$function$;

REVOKE ALL ON FUNCTION public.suly_ai_provider_config_get() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.suly_ai_provider_config_set(jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.suly_ai_provider_config_clear() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.suly_ai_provider_config_get() TO service_role;
GRANT EXECUTE ON FUNCTION public.suly_ai_provider_config_set(jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.suly_ai_provider_config_clear() TO service_role;
