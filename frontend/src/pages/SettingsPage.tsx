import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { TelegramConnectButton, TelegramStatus } from "../components/TelegramConnect";
import { Alert, Button, Card, Field, Select, Skeleton } from "../components/ui";
import { t } from "../i18n/uk";
import { api, ApiError } from "../lib/api";
import { meKey, useMe } from "../lib/auth";
import { listTimezones } from "../lib/format";
import { useTheme, type ThemeChoice } from "../lib/theme";

const themeLabels: Record<ThemeChoice, string> = {
  system: t.nav.themeSystem,
  light: t.nav.themeLight,
  dark: t.nav.themeDark,
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card as="section" className="p-5 sm:p-6">
      <h2 className="mb-4 text-xl">{title}</h2>
      {children}
    </Card>
  );
}

export default function SettingsPage() {
  const { data: user } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [theme, setTheme] = useTheme();
  const zones = useMemo(() => listTimezones(), []);
  const [timezone, setTimezone] = useState<string | null>(null);

  const saveTz = useMutation({
    mutationFn: (tz: string) => api.updateMe(tz),
    onSuccess: (updated) => {
      qc.setQueryData(meKey, updated);
      qc.invalidateQueries({ queryKey: ["topics"] });
      qc.invalidateQueries({ queryKey: ["topic"] });
    },
  });
  const unlink = useMutation({
    mutationFn: api.telegramUnlink,
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
  const logout = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      qc.clear();
      qc.setQueryData(meKey, null);
      navigate("/login", { replace: true });
    },
  });

  if (!user) return <Skeleton className="h-64 w-full rounded-xl" />;
  const currentTz = timezone ?? user.timezone;
  const options = zones.includes(user.timezone) ? zones : [user.timezone, ...zones];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl">{t.settings.title}</h1>

      <Section title={t.settings.account}>
        <p className="mb-4 font-mono text-sm text-muted">{user.email}</p>
        <div className="flex max-w-md flex-col gap-3">
          <Field label={t.settings.timezone} htmlFor="tz" hint={t.settings.timezoneHint}>
            <Select id="tz" value={currentTz} onChange={(e) => setTimezone(e.target.value)}>
              {options.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              disabled={currentTz === user.timezone}
              loading={saveTz.isPending}
              onClick={() => saveTz.mutate(currentTz)}
            >
              {t.common.save}
            </Button>
            {saveTz.isSuccess && currentTz === user.timezone && (
              <span className="text-sm text-success">✓ {t.settings.saved}</span>
            )}
          </div>
          {saveTz.error instanceof ApiError && <Alert>{saveTz.error.message}</Alert>}
        </div>
      </Section>

      <Section title={t.settings.telegram}>
        <div className="flex flex-col gap-4">
          <TelegramStatus user={user} />
          {user.telegram_blocked && <Alert tone="warning">{t.telegram.blocked}</Alert>}
          {user.telegram_linked ? (
            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => unlink.mutate()}
                loading={unlink.isPending}
              >
                {t.telegram.disconnect}
              </Button>
            </div>
          ) : (
            <TelegramConnectButton size="sm" />
          )}
        </div>
      </Section>

      <Section title={t.settings.appearance}>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t.settings.theme}>
          {(["system", "light", "dark"] as ThemeChoice[]).map((choice) => (
            <Button
              key={choice}
              size="sm"
              variant={theme === choice ? "primary" : "secondary"}
              role="radio"
              aria-checked={theme === choice}
              onClick={() => setTheme(choice)}
            >
              {themeLabels[choice]}
            </Button>
          ))}
        </div>
      </Section>

      <div>
        <Button variant="danger" onClick={() => logout.mutate()} loading={logout.isPending}>
          {t.settings.logout}
        </Button>
      </div>
    </div>
  );
}
