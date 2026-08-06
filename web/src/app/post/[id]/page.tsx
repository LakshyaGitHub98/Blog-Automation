"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, History } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { ScorePill, StatusPill } from "@/components/score";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type PostDetail } from "@/lib/api";

export default function PostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [detail, setDetail] = useState<PostDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .post(id)
      .then((d) => {
        if (active) setDetail(d);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "Not found");
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Alert variant="destructive">
          <AlertTitle>Could not load post</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const { post, revisions } = detail;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8">
      <div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/">
            <ArrowLeft className="size-4" />
            Back to list
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <StatusPill status={post.status} />
            <ScorePill score={post.final_score} label="AI score" />
            <span>detector: {post.detector || "—"}</span>
            <span>
              {post.iterations_used || 0} humanize pass
              {post.iterations_used === 1 ? "" : "es"}
            </span>
            <span className="tabular-nums">
              {post.created_at ? new Date(post.created_at).toLocaleString() : ""}
            </span>
          </div>
          <CardTitle className="text-2xl">{post.title || post.topic}</CardTitle>
          <CardDescription>{post.topic}</CardDescription>
        </CardHeader>
        <CardContent>
          {post.content ? (
            <Markdown>{post.content}</Markdown>
          ) : post.status === "failed" ? (
            <Alert variant="destructive">
              <AlertTitle>This generation failed</AlertTitle>
              <AlertDescription className="break-words">
                {post.error || "Unknown error"}
              </AlertDescription>
            </Alert>
          ) : (
            <p className="text-sm text-muted-foreground">No content yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" />
            Revisions (eval loop)
          </CardTitle>
          <CardDescription>
            Every scored version of the post, from draft to the best revision.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {revisions.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              No revisions recorded.
            </p>
          ) : (
            <Accordion type="multiple" defaultValue={[String(revisions.length - 1)]}>
              {[...revisions]
                .sort((a, b) => a.iteration - b.iteration)
                .map((rev) => (
                  <AccordionItem key={rev.id} value={String(rev.iteration)}>
                    <AccordionTrigger className="gap-3">
                      <span className="text-sm font-medium">
                        {rev.iteration === 0 ? "Draft" : `Humanize #${rev.iteration}`}
                      </span>
                      <ScorePill score={rev.ai_score} label="AI score" />
                    </AccordionTrigger>
                    <AccordionContent>
                      <Separator className="mb-4" />
                      <Markdown>{rev.content}</Markdown>
                    </AccordionContent>
                  </AccordionItem>
                ))}
            </Accordion>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
