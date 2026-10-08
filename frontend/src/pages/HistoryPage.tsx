import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Alert, Badge, Button, Card, EmptyState, Skeleton } from "../components/ui";
import { t } from "../i18n/uk";
import { api, type Digest } from "../lib/api";
import { useMe } from "../lib/auth";
import { formatDateTime, statusTone } from "../lib/format";
import { DigestMarkdown } from "../lib/markdown";

function DigestItem({
  digest,
  timezone,
  defaultOpen,
}: {
  digest: Digest;
  timezone?: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card as="article" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center justify-between gap-2 px-5 py-4 text-left hover:bg-surface-2/60"
      >
        <span className="flex flex-col">
          <span className="font-serif text-lg">
            {formatDateTime(digest.sent_at ?? digest.created_at, timezone)}
          </span>
          <span className="text-[13px] text-muted">{t.history.articles(digest.article_count)}</span>
        </span>
        <span className="flex items-center gap-3">
          <Badge tone={statusTone(digest.status)}>
            {t.history.status[digest.status] ?? digest.status}
          </Badge>
          <span className="text-[13px] text-muted">
            {open ? t.history.collapse : t.history.expand}
          </span>
        </span>
      </button>
      {open && (
        <div className="border-t border-border px-5 py-4">
          {digest.error && (
            <p className="mb-3 font-mono text-xs break-words text-warning">{digest.error}</p>
          )}
          <DigestMarkdown source={digest.content_markdown} />
        </div>
      )}
    </Card>
  );
}

export default function HistoryPage() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const { data: user } = useMe();
  const topic = useQuery({ queryKey: ["topic", id], queryFn: () => api.topic(id) });
  const digests = useQuery({
    queryKey: ["digests", id],
    queryFn: () => api.digests(id),
    // Pick up the result of a "send now" without a manual reload.
    refetchInterval: topic.data?.last_run_status === "queued" ? 3000 : false,
  });
  const run = useMutation({
    mutationFn: () => api.runTopic(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["topic", id] });
      setTimeout(() => qc.invalidateQueries({ queryKey: ["digests", id] }), 3000);
    },
  });

  if (topic.isError) {
    return (
      <EmptyState
        title={t.topic.notFound}
        action={
          <Link to="/">
            <Button variant="secondary">{t.common.back}</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to={`/topics/${id}`} className="text-[13px] text-muted hover:text-text">
          ← {topic.data?.name ?? t.nav.topics}
        </Link>
        <h1 className="mt-2 text-3xl">{t.history.title}</h1>
      </div>

      {run.isSuccess && <Alert tone="success">{t.topic.sendQueued}</Alert>}

      {digests.isPending && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}

      {digests.isError && <Alert>{t.common.unknownError}</Alert>}

      {digests.data && digests.data.length === 0 && (
        <EmptyState
          title={t.history.empty}
          text={t.history.emptyText}
          action={
            <Button onClick={() => run.mutate()} loading={run.isPending}>
              {t.topic.sendNow}
            </Button>
          }
        />
      )}

      {digests.data && digests.data.length > 0 && (
        <div className="flex flex-col gap-3">
          {digests.data.map((d, i) => (
            <DigestItem key={d.id} digest={d} timezone={user?.timezone} defaultOpen={i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}
