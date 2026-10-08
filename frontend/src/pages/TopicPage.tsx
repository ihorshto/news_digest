import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Select,
  Skeleton,
  Textarea,
} from "../components/ui";
import { t } from "../i18n/uk";
import {
  api,
  ApiError,
  type Frequency,
  type Meta,
  type Topic,
  type TopicInput,
  type TopicQueryInput,
} from "../lib/api";
import { useMe } from "../lib/auth";
import { formatDateTime, runStatusLabel, statusTone } from "../lib/format";
import { validateTopic, type TopicErrors } from "../lib/validation";

const FREQUENCIES: Frequency[] = ["hourly", "6h", "daily", "weekly"];
const HOURS = Array.from({ length: 24 }, (_, h) => h);

function errorText(err: unknown): string | null {
  if (!err) return null;
  return err instanceof ApiError ? err.message : t.common.unknownError;
}

const emptyForm: TopicInput = {
  name: "",
  description: "",
  language: "uk",
  frequency: "daily",
  send_hour: 8,
  weekday: 0,
  relevance_threshold: null,
};

function TopicForm({
  initial,
  meta,
  submitLabel,
  pendingLabel,
  onSubmit,
  pending,
  error,
  saved,
}: {
  initial: TopicInput;
  meta: Meta | undefined;
  submitLabel: string;
  pendingLabel: string;
  onSubmit: (input: TopicInput) => void;
  pending: boolean;
  error: string | null;
  saved?: boolean;
}) {
  const { data: user } = useMe();
  const [form, setForm] = useState<TopicInput>(initial);
  const [errors, setErrors] = useState<TopicErrors>({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  const set = <K extends keyof TopicInput>(key: K, value: TopicInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found = validateTopic(form.name, form.description);
    setErrors(found);
    if (Object.keys(found).length === 0) onSubmit(form);
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {error && <Alert>{error}</Alert>}
      <Field label={t.topic.name} htmlFor="name" error={errors.name}>
        <Input
          id="name"
          value={form.name}
          maxLength={200}
          placeholder={t.topic.namePlaceholder}
          onChange={(e) => set("name", e.target.value)}
          aria-invalid={!!errors.name}
        />
      </Field>
      <Field
        label={t.topic.description}
        htmlFor="description"
        error={errors.description}
        hint={t.topic.descriptionHint}
      >
        <Textarea
          id="description"
          rows={3}
          maxLength={2000}
          value={form.description}
          placeholder={t.topic.descriptionPlaceholder}
          onChange={(e) => set("description", e.target.value)}
          aria-invalid={!!errors.description}
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label={t.topic.language} htmlFor="language">
          <Select
            id="language"
            value={form.language}
            onChange={(e) => set("language", e.target.value)}
          >
            {Object.entries(meta?.languages ?? { uk: "Українська", en: "English" }).map(
              ([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ),
            )}
          </Select>
        </Field>
        <Field label={t.topic.frequency} htmlFor="frequency">
          <Select
            id="frequency"
            value={form.frequency}
            onChange={(e) => set("frequency", e.target.value as Frequency)}
          >
            {FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {t.frequency[f]}
              </option>
            ))}
          </Select>
        </Field>
        {form.frequency !== "hourly" && (
          <Field
            label={t.topic.sendHour}
            htmlFor="send_hour"
            hint={user ? t.topic.timezoneNote(user.timezone) : undefined}
          >
            <Select
              id="send_hour"
              value={form.send_hour}
              onChange={(e) => set("send_hour", Number(e.target.value))}
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </Select>
          </Field>
        )}
        {form.frequency === "weekly" && (
          <Field label={t.topic.weekday} htmlFor="weekday">
            <Select
              id="weekday"
              value={form.weekday}
              onChange={(e) => set("weekday", Number(e.target.value))}
            >
              {t.weekdays.map((day, i) => (
                <option key={day} value={i}>
                  {day}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </div>

      <div>
        <button
          type="button"
          className="text-[13px] text-muted hover:text-text"
          onClick={() => setShowAdvanced((v) => !v)}
          aria-expanded={showAdvanced}
        >
          {showAdvanced ? "▾" : "▸"} {t.topic.advanced}
        </button>
        {showAdvanced && (
          <div className="mt-3 max-w-xs">
            <Field label={t.topic.threshold} htmlFor="threshold" hint={t.topic.thresholdHint}>
              <Input
                id="threshold"
                type="number"
                min={0}
                max={1}
                step={0.01}
                className="font-mono"
                value={form.relevance_threshold ?? meta?.default_relevance_threshold ?? 0.3}
                onChange={(e) => set("relevance_threshold", Number(e.target.value))}
              />
            </Field>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" loading={pending}>
          {pending ? pendingLabel : submitLabel}
        </Button>
        {saved && !pending && <span className="text-sm text-success">✓ {t.topic.saved}</span>}
      </div>
    </form>
  );
}

function QueriesEditor({ topic, meta }: { topic: Topic; meta: Meta | undefined }) {
  const qc = useQueryClient();
  const toInputs = (tp: Topic): TopicQueryInput[] =>
    tp.queries.map(({ query, source, language }) => ({ query, source, language }));
  const [rows, setRows] = useState<TopicQueryInput[]>(() => toInputs(topic));
  const [dirty, setDirty] = useState(false);

  const onSaved = (updated: Topic) => {
    qc.setQueryData(["topic", topic.id], updated);
    qc.invalidateQueries({ queryKey: ["topics"] });
  };
  const save = useMutation({
    mutationFn: () =>
      api.replaceQueries(
        topic.id,
        rows.filter((r) => r.query.trim()),
      ),
    onSuccess: onSaved,
  });
  const regenerate = useMutation({
    mutationFn: () => api.regenerateQueries(topic.id),
    onSuccess: onSaved,
  });

  const update = (index: number, patch: Partial<TopicQueryInput>) => {
    setRows((r) => r.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setDirty(true);
  };

  return (
    <Card as="section" className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl">{t.topic.queriesTitle}</h2>
          <p className="mt-1 max-w-lg text-sm text-muted">{t.topic.queriesHint}</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => regenerate.mutate()}
          loading={regenerate.isPending}
        >
          {regenerate.isPending ? t.topic.regenerating : t.topic.regenerate}
        </Button>
      </div>

      {(save.error || regenerate.error) && (
        <div className="mt-4">
          <Alert>{errorText(save.error || regenerate.error)}</Alert>
        </div>
      )}

      <ul className="mt-5 flex flex-col gap-2">
        {rows.length === 0 && <li className="text-sm text-muted">{t.topic.queriesEmpty}</li>}
        {rows.map((row, i) => (
          <li
            key={i}
            className="grid grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_auto] items-center gap-2 border-b border-border pb-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_9.5rem_5rem_auto] sm:border-0 sm:pb-0"
          >
            <Input
              aria-label={t.topic.queriesTitle}
              className="col-span-3 font-mono text-[13px] sm:col-span-1"
              value={row.query}
              maxLength={300}
              onChange={(e) => update(i, { query: e.target.value })}
            />
            <Select
              aria-label="source"
              className="font-mono text-[13px]"
              value={row.source}
              onChange={(e) => update(i, { source: e.target.value as TopicQueryInput["source"] })}
            >
              <option value="google_news">{t.topic.source.google_news}</option>
              <option value="tavily">{t.topic.source.tavily}</option>
            </Select>
            <Select
              aria-label={t.topic.language}
              className="font-mono text-[13px]"
              value={row.language}
              onChange={(e) => update(i, { language: e.target.value })}
            >
              {Object.keys(meta?.languages ?? { en: "", uk: "" }).map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t.common.remove}
              onClick={() => {
                setRows((r) => r.filter((_, j) => j !== i));
                setDirty(true);
              }}
            >
              ✕
            </Button>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setRows((r) => [...r, { query: "", source: "google_news", language: "en" }]);
            setDirty(true);
          }}
        >
          + {t.common.add}
        </Button>
        {dirty && (
          <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>
            {t.topic.saveQueries}
          </Button>
        )}
      </div>
    </Card>
  );
}

function TopicActions({ topic }: { topic: Topic }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [queued, setQueued] = useState(false);

  const refresh = (updated?: Topic) => {
    if (updated) qc.setQueryData(["topic", topic.id], updated);
    qc.invalidateQueries({ queryKey: ["topics"] });
  };
  const run = useMutation({
    mutationFn: () => api.runTopic(topic.id),
    onSuccess: () => {
      setQueued(true);
      qc.invalidateQueries({ queryKey: ["topic", topic.id] });
    },
  });
  const toggle = useMutation({
    mutationFn: () => api.updateTopic(topic.id, { is_active: !topic.is_active }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api.deleteTopic(topic.id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["topic", topic.id] });
      qc.invalidateQueries({ queryKey: ["topics"] });
      navigate("/", { replace: true });
    },
  });

  const error = errorText(run.error || toggle.error || remove.error);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => run.mutate()} loading={run.isPending}>
          {run.isPending ? t.topic.sending : t.topic.sendNow}
        </Button>
        <Button variant="secondary" onClick={() => toggle.mutate()} loading={toggle.isPending}>
          {topic.is_active ? t.topic.pause : t.topic.resume}
        </Button>
        <Link to={`/topics/${topic.id}/history`}>
          <Button variant="ghost">{t.topic.viewHistory}</Button>
        </Link>
        <Button
          variant="danger"
          className="sm:ml-auto"
          onClick={() => window.confirm(t.topic.deleteConfirm) && remove.mutate()}
          loading={remove.isPending}
        >
          {t.common.delete}
        </Button>
      </div>
      {queued && <Alert tone="success">{t.topic.sendQueued}</Alert>}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}

function EditTopic({ id, meta }: { id: number; meta: Meta | undefined }) {
  const qc = useQueryClient();
  const { data: user } = useMe();
  const topic = useQuery({
    queryKey: ["topic", id],
    queryFn: () => api.topic(id),
    // While a run is queued, refresh to show its outcome.
    refetchInterval: (query) => (query.state.data?.last_run_status === "queued" ? 3000 : false),
  });
  const save = useMutation({
    mutationFn: (input: TopicInput) => api.updateTopic(id, input),
    onSuccess: (updated) => {
      qc.setQueryData(["topic", id], updated);
      qc.invalidateQueries({ queryKey: ["topics"] });
    },
  });

  if (topic.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-72 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }
  if (topic.isError || !topic.data) {
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
  const data = topic.data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/" className="text-[13px] text-muted hover:text-text">
          ← {t.nav.topics}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl">{data.name}</h1>
          <Badge tone={data.is_active ? "success" : "neutral"}>
            {data.is_active ? t.dashboard.active : t.dashboard.paused}
          </Badge>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-faint">
          <span>
            {t.topic.nextRun}:{" "}
            {data.is_active ? formatDateTime(data.next_run_at, user?.timezone) : "—"}
          </span>
          <span>
            {t.dashboard.lastRun}: {formatDateTime(data.last_run_at, user?.timezone)}
          </span>
          {data.last_run_status && (
            <Badge tone={statusTone(data.last_run_status)}>
              {runStatusLabel(data.last_run_status)}
            </Badge>
          )}
        </div>
      </div>

      <TopicActions topic={data} />

      {/* Remount when the saved queries change so local edits reset to the server state. */}
      <QueriesEditor key={data.queries.map((q) => q.id).join(",")} topic={data} meta={meta} />

      <Card as="section" className="p-5 sm:p-6">
        <TopicForm
          key={data.id}
          meta={meta}
          initial={{
            name: data.name,
            description: data.description,
            language: data.language,
            frequency: data.frequency,
            send_hour: data.send_hour,
            weekday: data.weekday,
            relevance_threshold: data.relevance_threshold,
          }}
          submitLabel={t.common.save}
          pendingLabel={t.common.saving}
          onSubmit={(input) => save.mutate(input)}
          pending={save.isPending}
          error={errorText(save.error)}
          saved={save.isSuccess}
        />
      </Card>
    </div>
  );
}

function NewTopic({ meta }: { meta: Meta | undefined }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const create = useMutation({
    mutationFn: (input: TopicInput) => api.createTopic(input),
    onSuccess: (topic) => {
      qc.setQueryData(["topic", topic.id], topic);
      qc.invalidateQueries({ queryKey: ["topics"] });
      navigate(`/topics/${topic.id}`, { replace: true });
    },
  });
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/" className="text-[13px] text-muted hover:text-text">
          ← {t.nav.topics}
        </Link>
        <h1 className="mt-2 text-3xl">{t.topic.newTitle}</h1>
      </div>
      <Card as="section" className="p-5 sm:p-6">
        <TopicForm
          meta={meta}
          initial={emptyForm}
          submitLabel={t.topic.create}
          pendingLabel={t.topic.creating}
          onSubmit={(input) =>
            create.mutate({ ...input, relevance_threshold: input.relevance_threshold || null })
          }
          pending={create.isPending}
          error={errorText(create.error)}
        />
      </Card>
    </div>
  );
}

export default function TopicPage() {
  const { id } = useParams();
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: 60_000 });
  if (!id) return <NewTopic meta={meta} />;
  const numeric = Number(id);
  if (!Number.isInteger(numeric)) return <EmptyState title={t.topic.notFound} />;
  return <EditTopic id={numeric} meta={meta} />;
}
