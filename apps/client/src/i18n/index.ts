export const messages = {
  ar: {
    wordmark: "SULY",
    tagline: "More Than AI. Your Intelligent Partner.",
    welcome: "أهلاً بك في سولي",
    description: "شريكك الذكي للبحث والتخطيط والإبداع وتنفيذ المهام.",
    status: "المنصة قيد التأسيس",
    footer: "SULY TECHNOLOGIES",
  },
  en: {
    wordmark: "SULY",
    tagline: "More Than AI. Your Intelligent Partner.",
    welcome: "Welcome to SULY",
    description: "Your intelligent partner for research, planning, creation, and task execution.",
    status: "Platform foundation in progress",
    footer: "SULY TECHNOLOGIES",
  },
} as const;

export type Locale = keyof typeof messages;
export type MessageKey = keyof typeof messages.ar;

export function getMessages(locale: Locale) {
  return messages[locale];
}

export function getDirection(locale: Locale): "rtl" | "ltr" {
  return locale === "ar" ? "rtl" : "ltr";
}
