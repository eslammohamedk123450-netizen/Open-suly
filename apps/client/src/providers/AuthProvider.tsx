import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { Linking } from "react-native";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";

type AuthContextValue = {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  user: User | null;
  profile: { display_name: string | null; avatar_url: string | null; locale: "ar" | "en" } | null;
  signIn: (email: string, password: string) => Promise<string | null>;
  signUp: (email: string, password: string, displayName: string) => Promise<{ error: string | null; needsEmailConfirmation: boolean }>;
  signOut: () => Promise<string | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<{ display_name: string | null; avatar_url: string | null; locale: "ar" | "en" } | null>(null);

  useEffect(() => {
    const client = supabase;
    if (!client) {
      setLoading(false);
      return;
    }

    let alive = true;
    const handleDeepLink = async (url: string | null | undefined) => {
      if (!url || !url.includes("code=")) return;
      try {
        await client.auth.exchangeCodeForSession(url);
      } catch {
        // The normal session listener below remains the source of truth.
      }
    };

    void client.auth.getSession().then(
      ({ data, error }) => {
        if (!alive) return;
        if (!error) setSession(data.session);
        setLoading(false);
      },
      () => {
        if (alive) setLoading(false);
      },
    );

    const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });
    void Linking.getInitialURL().then(handleDeepLink, () => undefined);
    const linkSubscription = Linking.addEventListener("url", ({ url }) => { void handleDeepLink(url); });

    return () => {
      alive = false;
      subscription.unsubscribe();
      linkSubscription.remove();
    };
  }, []);

  useEffect(() => {
    const client = supabase;
    if (!client || !session?.user.id) {
      setProfile(null);
      return;
    }
    let active = true;
    setProfile(null);
    void client.from("profiles").select("display_name, avatar_url, locale").eq("id", session.user.id).maybeSingle()
      .then(({ data, error }) => {
        if (active && !error) setProfile(data);
      }, () => undefined);
    return () => { active = false; };
  }, [session?.user.id]);

  const value = useMemo<AuthContextValue>(() => ({
    configured: isSupabaseConfigured,
    loading,
    session,
    user: session?.user ?? null,
    profile,
    signIn: async (email, password) => {
      const client = supabase;
      if (!client) return "إعدادات الاتصال بـ Supabase غير مكتملة.";
      const { error } = await client.auth.signInWithPassword({ email: email.trim(), password });
      return error?.message ?? null;
    },
    signUp: async (email, password, displayName) => {
      const client = supabase;
      if (!client) return { error: "إعدادات الاتصال بـ Supabase غير مكتملة.", needsEmailConfirmation: false };
      const { data, error } = await client.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: { display_name: displayName.trim() },
        },
      });
      return {
        error: error?.message ?? null,
        needsEmailConfirmation: !error && !data.session,
      };
    },
    signOut: async () => {
      const client = supabase;
      if (!client) return "إعدادات الاتصال بـ Supabase غير مكتملة.";
      const { error } = await client.auth.signOut();
      return error?.message ?? null;
    },
  }), [loading, profile, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
