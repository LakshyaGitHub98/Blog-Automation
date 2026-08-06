"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { ScorePill, StatusPill } from "@/components/score";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { useGeneration } from "@/hooks/use-generation";
import { api, type Post } from "@/lib/api";
import { cn } from "@/lib/utils";

const STAGES: Record<string, string> = {
  queued: "Waiting in queue…",
  draft: "Drafting with the LLM…",
  evaluating: "Scoring with the AI detector…",
  humanizing: "Rewriting to sound human…",
  saving: "Saving the best revision…",
  done: "Done",
  failed: "Failed",
};

export default function HomePage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-8">
      <GenerateForm />
      <PostsSection />
    </div>
  );
}

function GenerateForm() {
  const router = useRouter();
  const { job, polling, startPolling } = useGeneration();

  const [topic, setTopic] = useState("");
  const [threshold, setThreshold] = useState(0.6);
  const [maxIterations, setMaxIterations] = useState(2);
  const [temperature, setTemperature] = useState(0.85);
  const [maxTokens, setMaxTokens] = useState("2048");
  const [submitting, setSubmitting] = useState(false);

  const busy = submitting || polling;

  const submit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setSubmitting(true);
      try {
        const res = await api.generate({
          topic,
          threshold,
          max_iterations: maxIterations,
          temperature,
          max_tokens: parseInt(maxTokens, 10),
        });
        toast.success(`Queued — ${res.request_id}`);
        startPolling(res.request_id);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to start");
      } finally {
        setSubmitting(false);
      }
    },
    [topic, threshold, maxIterations, temperature, maxTokens, startPolling]
  );

  const stage = job?.stage ?? "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4" />
          Generate a blog post
        </CardTitle>
        <CardDescription>
          Draft it, score it with the detector, then humanize it until it passes.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="topic">Topic</Label>
            <Textarea
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. How I scaled my side project to 10k users"
              className="min-h-20"
              required
            />
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="threshold">
                AI threshold{" "}
                <span className="text-muted-foreground tabular-nums">
                  {threshold.toFixed(2)}
                </span>
              </Label>
              <Slider
                id="threshold"
                min={0.3}
                max={0.8}
                step={0.05}
                value={[threshold]}
                onValueChange={(v) => setThreshold(v[0])}
                disabled={busy}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="iterations">
                Max humanize iterations{" "}
                <span className="text-muted-foreground tabular-nums">
                  {maxIterations}
                </span>
              </Label>
              <Slider
                id="iterations"
                min={0}
                max={4}
                step={1}
                value={[maxIterations]}
                onValueChange={(v) => setMaxIterations(v[0])}
                disabled={busy}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="temperature">
                Temperature{" "}
                <span className="text-muted-foreground tabular-nums">
                  {temperature.toFixed(2)}
                </span>
              </Label>
              <Slider
                id="temperature"
                min={0.2}
                max={1.5}
                step={0.05}
                value={[temperature]}
                onValueChange={(v) => setTemperature(v[0])}
                disabled={busy}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_tokens">Max tokens</Label>
              <Select
                value={maxTokens}
                onValueChange={setMaxTokens}
                disabled={busy}
              >
                <SelectTrigger id="max_tokens" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="2048">2048</SelectItem>
                  <SelectItem value="4096">4096</SelectItem>
                  <SelectItem value="8192">8192</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button type="submit" disabled={busy || !topic.trim()} className="w-full sm:w-auto">
            {submitting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            {busy ? "Working…" : "Generate"}
          </Button>
        </form>

        {job && polling && (
          <div className="mt-6 space-y-3">
            <Separator />
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium capitalize">
                {STAGES[stage] ?? stage}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {job.elapsed_seconds ?? 0}s
              </span>
            </div>
            <div className="relative h-1 w-full overflow-hidden rounded-full bg-muted">
              <div className="absolute inset-y-0 w-1/3 animate-pulse rounded-full bg-primary" />
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="size-3 animate-spin" />
              {job.request_id.slice(0, 8)} — detector is scoring each paragraph
            </div>
          </div>
        )}

        {job && job.status === "failed" && (
          <Alert variant="destructive" className="mt-6">
            <AlertTitle>Generation failed</AlertTitle>
            <AlertDescription className="break-words">
              {job.error || "Unknown error"}
            </AlertDescription>
            {job.error?.toLowerCase().includes("rate limit") && (
              <AlertDescription className="mt-2">
                Rate-limited by the provider. Wait about a minute, then hit
                Generate again — the app already retries automatically.
              </AlertDescription>
            )}
          </Alert>
        )}

        {job && job.status === "completed" && (
          <div className="mt-6 flex flex-col gap-3">
            <Separator />
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium">{job.title}</span>
              <ScorePill score={job.final_score} label="AI score" />
              <span className="text-xs text-muted-foreground">
                {job.iterations_used} humanize pass
                {job.iterations_used === 1 ? "" : "es"}
              </span>
            </div>
            <Button variant="outline" onClick={() => router.push(`/post/${job.request_id}`)}>
              View result
              <ArrowRight className="size-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PostsSection() {
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    api
      .posts()
      .then((r) => {
        if (active) setPosts(r.posts);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "Failed to load");
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);

  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Recent posts</CardTitle>
          <CardDescription>Generated by the pipeline</CardDescription>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={refresh} aria-label="Refresh">
          <RefreshCw className="size-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-1">
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : posts == null ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : posts.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No posts yet. Generate your first one above.
          </p>
        ) : (
          posts.map((p) => <PostRow key={p.id} post={p} />)
        )}
      </CardContent>
    </Card>
  );
}

function PostRow({ post }: { post: Post }) {
  return (
    <Link
      href={`/post/${post.id}`}
      className={cn(
        "-mx-2 flex flex-col gap-1.5 rounded-lg px-2 py-3 transition-colors hover:bg-muted/60",
        (post.status === "queued" || post.status === "generating") &&
          "pointer-events-none opacity-60"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <StatusPill status={post.status} />
        <ScorePill score={post.final_score} label="AI score" />
        <span>detector: {post.detector || "—"}</span>
        <span>
          {post.iterations_used || 0} pass{post.iterations_used === 1 ? "" : "es"}
        </span>
        <span className="tabular-nums">
          {post.created_at ? new Date(post.created_at).toLocaleString() : ""}
        </span>
      </div>
      <span className="font-medium">{post.title || post.topic}</span>
      {post.error && (
        <span className="truncate text-xs text-destructive">{post.error}</span>
      )}
    </Link>
  );
}
