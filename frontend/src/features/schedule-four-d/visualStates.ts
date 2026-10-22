import type { FourDItem } from "./types";

export const fourDColors: Record<string, string> = {
  NOT_STARTED: "#8a9ba8",
  IN_PROGRESS: "#2196d2",
  COMPLETED: "#208552",
  LATE: "#dd8b1b",
  DELAYED: "#dd8b1b",
  CRITICAL: "#c44343",
  NEAR_CRITICAL: "#ad669b",
  BLOCKED_BY_READINESS: "#e06b18",
  REMOVED: "#7a7584",
  TEMPORARY: "#9a7b25",
  MAINTENANCE: "#7b65c2",
  UNKNOWN: "#697582",
};
export function itemVisual(item: FourDItem, configured: Record<string, unknown> = {}) {
  const priority = [
    "BLOCKED_BY_READINESS",
    "CRITICAL",
    "NEAR_CRITICAL",
    "DELAYED",
    "LATE",
    "MAINTENANCE",
    "TEMPORARY",
    "REMOVED",
  ];
  const semanticClass = priority.find((state) => item.visual_classes.includes(state)) ?? item.state ?? "UNKNOWN";
  const override = configured[semanticClass];
  const configuredState = override && typeof override === "object" ? (override as Record<string, unknown>) : {};
  const configuredColor = configuredState.color ?? override;
  const color =
    typeof configuredColor === "string" && /^#[0-9a-f]{6}$/i.test(configuredColor)
      ? configuredColor
      : (fourDColors[semanticClass] ?? fourDColors.UNKNOWN);
  const opacity =
    typeof configuredState.opacity === "number" && configuredState.opacity >= 0 && configuredState.opacity <= 1
      ? configuredState.opacity
      : 1;
  return { color, visible: item.visible === true, semanticClass, opacity };
}
export function shiftFourDDate(value: string, days: number): string {
  const hasTime = value.includes("T");
  const hasZone = /Z$|[+-]\d{2}:\d{2}$/.test(value);
  const date = new Date(hasTime ? (hasZone ? value : `${value}Z`) : `${value}T12:00:00Z`);
  if (!Number.isFinite(date.valueOf())) return value;
  date.setUTCDate(date.getUTCDate() + days);
  return hasTime ? (hasZone ? date.toISOString() : date.toISOString().slice(0, 16)) : date.toISOString().slice(0, 10);
}

export function fourDDateInput(value: string, timezone = "UTC") {
  if (!value) return "";
  if (!/Z$|[+-]\d{2}:\d{2}$/.test(value))
    return value.includes("T") ? value.slice(0, 16) : `${value.slice(0, 10)}T00:00`;
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}
