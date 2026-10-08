import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Alert, Button, Card, Field, Input, Logo } from "../components/ui";
import { ThemeToggle } from "../components/ThemeToggle";
import { t } from "../i18n/uk";
import { api, ApiError } from "../lib/api";
import { useSetMe } from "../lib/auth";
import { validateAuth, type AuthErrors } from "../lib/validation";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const isRegister = mode === "register";
  const navigate = useNavigate();
  const location = useLocation();
  const setMe = useSetMe();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<AuthErrors>({});

  const mutation = useMutation({
    mutationFn: () => {
      if (isRegister) {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        return api.register(email.trim(), password, tz);
      }
      return api.login(email.trim(), password);
    },
    onSuccess: (user) => {
      setMe(user);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(isRegister ? "/topics/new" : from || "/", { replace: true });
    },
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const found = validateAuth(email, password, mode, isRegister ? confirm : undefined);
    setErrors(found);
    if (Object.keys(found).length === 0) mutation.mutate();
  };

  const apiError = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <div className="flex min-h-dvh flex-col">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-start justify-center px-4 pt-[6vh] pb-16">
        <div className="w-full max-w-[400px]">
          <div className="mb-8 text-center">
            <Logo className="text-[28px]" />
            <p className="mt-2 text-sm text-muted">{t.tagline}</p>
          </div>
          <Card className="p-6 sm:p-8">
            <h1 className="text-2xl">{isRegister ? t.auth.registerTitle : t.auth.loginTitle}</h1>
            <p className="mt-1 text-sm text-muted">
              {isRegister ? t.auth.registerSubtitle : t.auth.loginSubtitle}
            </p>
            <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit} noValidate>
              {apiError && <Alert>{apiError}</Alert>}
              <Field label={t.auth.email} htmlFor="email" error={errors.email}>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!errors.email}
                  autoFocus
                />
              </Field>
              <Field
                label={t.auth.password}
                htmlFor="password"
                error={errors.password}
                hint={isRegister ? t.auth.passwordHint : undefined}
              >
                <Input
                  id="password"
                  type="password"
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-invalid={!!errors.password}
                />
              </Field>
              {isRegister && (
                <Field label={t.auth.passwordConfirm} htmlFor="confirm" error={errors.confirm}>
                  <Input
                    id="confirm"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    aria-invalid={!!errors.confirm}
                  />
                </Field>
              )}
              <Button type="submit" className="mt-2 w-full" loading={mutation.isPending}>
                {isRegister ? t.auth.registerButton : t.auth.loginButton}
              </Button>
            </form>
          </Card>
          <p className="mt-6 text-center text-sm text-muted">
            {isRegister ? t.auth.haveAccount : t.auth.noAccount}{" "}
            <Link
              to={isRegister ? "/login" : "/register"}
              className="font-medium text-accent hover:underline"
            >
              {isRegister ? t.auth.toLogin : t.auth.toRegister}
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
