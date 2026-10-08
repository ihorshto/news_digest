import { t } from "../i18n/uk";
import type { Topic } from "./api";

export function formatDateTime(iso: string | null, timeZone?: string): string {
  if (!iso) return t.common.never;
  const date = new Date(iso);
  try {
    return new Intl.DateTimeFormat("uk-UA", {
      timeZone,
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return date.toLocaleString("uk-UA");
  }
}

export function scheduleLabel(topic: Topic): string {
  const freq = t.frequency[topic.frequency] ?? topic.frequency;
  const hour = `${String(topic.send_hour).padStart(2, "0")}:00`;
  if (topic.frequency === "daily") return `${freq} о ${hour}`;
  if (topic.frequency === "weekly") return `${freq}, ${t.weekdays[topic.weekday]} о ${hour}`;
  return freq;
}

export function listTimezones(): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  try {
    const zones = intl.supportedValuesOf?.("timeZone");
    if (zones && zones.length) return zones;
  } catch {
    // older browsers
  }
  return ["Europe/Kyiv", "Europe/Paris", "Europe/London", "America/New_York", "UTC"];
}

export function statusTone(status: string | null): "success" | "warning" | "danger" | "neutral" {
  if (!status) return "neutral";
  if (status === "sent" || status === "fake_sent") return "success";
  if (status.startsWith("error") || status === "failed") return "danger";
  if (status === "no_chat") return "warning";
  return "neutral";
}

export function runStatusLabel(status: string): string {
  const key = status.startsWith("error") ? "error" : status;
  return t.runStatus[key] ?? status;
}
