import { t } from "../i18n/uk";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type AuthErrors = { email?: string; password?: string; confirm?: string };

export function validateAuth(
  email: string,
  password: string,
  mode: "login" | "register",
  confirm?: string,
): AuthErrors {
  const errors: AuthErrors = {};
  const e = t.auth.errors;
  if (!email.trim()) errors.email = e.emailRequired;
  else if (!EMAIL_RE.test(email.trim())) errors.email = e.emailInvalid;

  if (!password) errors.password = e.passwordRequired;
  else if (mode === "register" && password.length < 8) errors.password = e.passwordShort;

  if (mode === "register" && confirm !== undefined && confirm !== password) {
    errors.confirm = e.passwordMismatch;
  }
  return errors;
}

export type TopicErrors = { name?: string; description?: string };

export function validateTopic(name: string, description: string): TopicErrors {
  const errors: TopicErrors = {};
  if (!name.trim()) errors.name = t.topic.errors.nameRequired;
  if (description.trim().length < 3) errors.description = t.topic.errors.descriptionShort;
  return errors;
}
