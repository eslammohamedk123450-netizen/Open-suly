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
    if (!supabase) {
      setLoading(false);
      return;
    }

    let alive = true;
    const handleDeepLink = async (url: string | null) => {
      if (!url || !url.includes("code=")) return;
      try {
        await supabase.auth.exchangeCodeForSession(url);
      } catch {
        // The normal session listener below remains the source of truth.
      }
    };

    supabase.auth.getSession().then(({ data, error }) => {
      if (!alive) return;
      if (!error) setSession(data.session);
      setLoading(false);
    }).catch(() => {
      if (alive) setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });
    Linking.getInitialURL().then(handleDeepLink).catch(() => undefined);
    const linkSubscription = Linking.addEventListener("url", ({ url }) => { void handleDeepLink(url); });

    return () => {
      alive = false;
      subscription.unsubscribe();
      linkSubscription.remove();
    };
  }, []);

  useEffect(() => {
    if (!supabase || !session?.user.id) {
      setProfile(null);
      return;
    }
    let active = true;
    supabase.from("profiles").select("display_name, avatar_url, locale").eq("id", session.user.id).maybeSingle()
      .then(({ data, error }) => {
        if (active && !error) setProfile(data);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [session?.user.id]);

  const value = useMemo<AuthContextValue>(() => ({
    configured: isSupabaseConfigured,
    loading,
    session,
    user: session?.user ?? null,
    profile,
    signIn: async (email, password) => {
      if (!supabase) return "إعدادات الاتصال بـ Supabase غير مكتملة.";
      const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      return error?.message ?? null;
    },
    signUp: async (email, password, displayName) => {
      if (!supabase) return { error: "إعدادات الاتصال بـ Supabase غير مكتملة.", needsEmailConfirmation: false };
      const { data, error } = await supabase.auth.signUp({
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
      if (!supabase) return "إعدادات الاتصال بـ Supabase غير مكتملة.";
      const { error } = await supabase.auth.signOut();
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
