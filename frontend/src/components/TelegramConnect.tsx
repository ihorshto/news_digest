import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../i18n/uk";
import { api, ApiError, type TelegramLink, type User } from "../lib/api";
import { meKey, useMe } from "../lib/auth";
import { Alert, Button } from "./ui";

/** Opens the bot deep link and polls /me every 3 s until the chat is linked. */
export function useTelegramConnect() {
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const { data: user } = useMe();
  const qc = useQueryClient();
  const waiting = !!linkUrl && !user?.telegram_linked;

  // Poll every 3 s while waiting and the tab is visible; the result goes into the
  // shared "me" cache so every component sees the new status at once.
  useQuery({
    queryKey: ["telegram-poll"],
    queryFn: async () => {
      const me = await api.me();
      qc.setQueryData(meKey, me);
      return me.telegram_linked;
    },
    enabled: waiting,
    refetchInterval: waiting ? 3000 : false,
    refetchIntervalInBackground: false,
  });

  const mutation = useMutation<TelegramLink, Error, Window | null>({
    mutationFn: () => api.telegramLink(),
    onSuccess: (link, popup) => {
      setLinkUrl(link.url);
      if (popup && !popup.closed) popup.location.href = link.url;
      else window.location.href = link.url; // popup blocked: navigate in place
    },
    onError: (_err, popup) => popup?.close(),
  });

  const connect = () => {
    // Open the tab synchronously inside the click handler so popup blockers allow it,
    // then point it at the deep link once the token is ready.
    const popup = window.open("", "_blank");
    if (popup) popup.opener = null;
    mutation.mutate(popup);
  };

  return { connect, mutation, linkUrl, waiting };
}

export function TelegramConnectButton({ size = "md" }: { size?: "sm" | "md" }) {
  const { connect, mutation, linkUrl, waiting } = useTelegramConnect();
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: 60_000 });
  const error = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button size={size} onClick={connect} loading={mutation.isPending}>
          {t.telegram.connect}
        </Button>
        {waiting && linkUrl && (
          <a
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-accent hover:underline"
          >
            {t.telegram.openAgain}
          </a>
        )}
      </div>
      {waiting && <p className="text-sm text-muted">{t.telegram.waiting}</p>}
      {meta?.fake_telegram && <p className="text-[13px] text-faint">{t.telegram.fakeMode}</p>}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}

export function TelegramStatus({ user }: { user: User }) {
  if (user.telegram_linked) {
    return (
      <span className="inline-flex items-center gap-2 text-sm text-success">
        <span className="h-2 w-2 rounded-full bg-success" />
        {user.telegram_username
          ? t.telegram.connectedAs(user.telegram_username)
          : t.telegram.connected}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted">
      <span className="h-2 w-2 rounded-full bg-faint" />
      {t.telegram.notConnected}
    </span>
  );
}
