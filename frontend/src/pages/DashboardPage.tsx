import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { TelegramConnectButton } from "../components/TelegramConnect";
import { Alert, Badge, Button, Card, EmptyState, Skeleton } from "../components/ui";
import { t } from "../i18n/uk";
import { api, type Topic } from "../lib/api";
import { useMe } from "../lib/auth";
import { formatDateTime, runStatusLabel, scheduleLabel, statusTone } from "../lib/format";

function TopicCard({ topic, timezone }: { topic: Topic; timezone: string }) {
  return (
    <Card as="article" className="group relative p-5 transition-colors hover:border-border-strong">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-xl">
          <Link to={`/topics/${topic.id}`} className="after:absolute after:inset-0">
            {topic.name}
          </Link>
        </h2>
        <Badge tone={topic.is_active ? "success" : "neutral"}>
          {topic.is_active ? t.dashboard.active : t.dashboard.paused}
        </Badge>
      </div>
      <p className="mt-1.5 line-clamp-2 text-sm text-muted">{topic.description}</p>
      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-3">
        <div className="flex gap-1.5 sm:flex-col sm:gap-0">
          <dt className="text-faint">{t.topic.frequency}</dt>
          <dd>{scheduleLabel(topic)}</dd>
        </div>
        <div className="flex gap-1.5 sm:flex-col sm:gap-0">
          <dt className="text-faint">{t.dashboard.nextRun}</dt>
          <dd>{topic.is_active ? formatDateTime(topic.next_run_at, timezone) : "—"}</dd>
        </div>
        <div className="flex gap-1.5 sm:flex-col sm:gap-0">
          <dt className="text-faint">{t.history.title}</dt>
          <dd>{t.dashboard.digests(topic.digest_count)}</dd>
        </div>
      </dl>
      <div className="relative mt-4 flex items-center justify-between gap-3 border-t border-border pt-3">
        {topic.last_run_status ? (
          <Badge tone={statusTone(topic.last_run_status)}>
            {t.topic.lastStatus}: {runStatusLabel(topic.last_run_status)}
          </Badge>
        ) : (
          <span />
        )}
        <Link
          to={`/topics/${topic.id}/history`}
          className="relative z-[1] text-[13px] font-medium text-accent hover:underline"
        >
          {t.dashboard.history} →
        </Link>
      </div>
    </Card>
  );
}

function TelegramBanner({ blocked }: { blocked: boolean }) {
  return (
    <Card className="mb-8 border-accent/30 bg-accent-soft/40 p-5">
      <h2 className="text-lg">{t.telegram.bannerTitle}</h2>
      <p className="mt-1 mb-4 text-sm text-muted">
        {blocked ? t.telegram.blocked : t.telegram.bannerText}
      </p>
      <TelegramConnectButton size="sm" />
    </Card>
  );
}

export default function DashboardPage() {
  const { data: user } = useMe();
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: 60_000 });
  const topics = useQuery({ queryKey: ["topics"], queryFn: api.topics });
  const max = meta?.max_topics_per_user ?? 10;
  const count = topics.data?.length ?? 0;

  return (
    <div>
      {user && !user.telegram_linked && <TelegramBanner blocked={user.telegram_blocked} />}

      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl">{t.dashboard.title}</h1>
          {topics.data && topics.data.length > 0 && (
            <p className="mt-1 font-mono text-xs text-faint">{t.dashboard.limit(count, max)}</p>
          )}
        </div>
        {topics.data && topics.data.length > 0 && count < max && (
          <Link to="/topics/new">
            <Button>+ {t.dashboard.newTopic}</Button>
          </Link>
        )}
      </div>

      {topics.isPending && (
        <div className="grid gap-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 w-full rounded-xl" />
          ))}
        </div>
      )}

      {topics.isError && (
        <Alert>
          {t.dashboard.loadError}.{" "}
          <button className="underline" onClick={() => topics.refetch()}>
            {t.common.retry}
          </button>
        </Alert>
      )}

      {topics.data && topics.data.length === 0 && (
        <EmptyState
          title={t.dashboard.emptyTitle}
          text={t.dashboard.emptyText}
          action={
            <Link to="/topics/new">
              <Button>{t.dashboard.emptyCta}</Button>
            </Link>
          }
        />
      )}

      {topics.data && topics.data.length > 0 && (
        <div className="grid gap-4">
          {topics.data.map((topic) => (
            <TopicCard key={topic.id} topic={topic} timezone={user?.timezone ?? "UTC"} />
          ))}
        </div>
      )}
    </div>
  );
}
