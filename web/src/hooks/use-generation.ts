"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, type JobStatus } from "@/lib/api";

export function useGeneration() {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    setPolling(false);
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      stop();
      setJob({
        request_id: id,
        status: "queued",
        stage: "queued",
        error: "",
        title: "",
        final_score: null,
        iterations_used: 0,
        detector: "",
        elapsed_seconds: 0,
      });
      setPolling(true);
      timerRef.current = setInterval(async () => {
        try {
          const s = await api.status(id);
          setJob(s);
          if (s.status === "completed" || s.status === "failed") {
            stop();
          }
        } catch {
          stop();
        }
      }, 2000);
    },
    [stop]
  );

  useEffect(() => () => stop(), [stop]);

  return { job, polling, startPolling, stop };
}
