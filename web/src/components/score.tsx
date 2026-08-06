import { cn } from "@/lib/utils";

export function scoreTone(score: number | null | undefined) {
  if (score == null) return "text-muted-foreground border-border";
  if (score < 0.4) return "text-emerald-500 border-emerald-500/40";
  if (score < 0.6) return "text-amber-500 border-amber-500/40";
  return "text-red-500 border-red-500/40";
}

export function ScorePill({
  score,
  label,
}: {
  score: number | null | undefined;
  label?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums",
        scoreTone(score)
      )}
    >
      {label ? `${label}: ` : ""}
      {score == null ? "—" : score.toFixed(3)}
    </span>
  );
}

const statusTone: Record<string, string> = {
  completed: "text-emerald-500 border-emerald-500/40",
  failed: "text-red-500 border-red-500/40",
  queued: "text-amber-500 border-amber-500/40",
  generating: "text-amber-500 border-amber-500/40",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        statusTone[status] ?? "text-muted-foreground border-border"
      )}
    >
      {status}
    </span>
  );
}
