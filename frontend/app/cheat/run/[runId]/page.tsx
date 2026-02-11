"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { api, isApiError, hasToken } from "@/lib/api";
import { TID } from "@/lib/testids";
import { ErrorBox } from "@/components/ErrorBox";

interface StepInfo {
  step_number: number;
  title: string;
  status: string;
}

interface CheatCodeInfo {
  id: string;
  code: string;
  title: string;
}

interface RunData {
  id: string;
  status: string;
  total_steps: number;
  completed_steps: number;
  cheat_code: CheatCodeInfo;
  steps?: StepInfo[];
}

export default function RunPage() {
  const router = useRouter();
  const params = useParams();
  const runId = params.runId as string;
  const [run, setRun] = useState<RunData | null>(null);
  const [title, setTitle] = useState("Cheat Code Run");
  const [firstWin, setFirstWin] = useState(false);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);

  const loadRun = useCallback(async function loadRun() {
    try {
      const { data } = await api.get(`/cheat-codes/runs/${runId}`);
      setRun(data);
      // Set title from cheat code
      if (data.cheat_code?.title) {
        setTitle(data.cheat_code.title);
      }
    } catch (err) {
      if (isApiError(err)) {
        setError(err.message);
        setRequestId(err.requestId);
      }
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (!hasToken()) { router.replace("/login"); return; }
    loadRun();
  }, [loadRun, router]);

  async function completeStep1() {
    setError("");
    setRequestId(null);
    setCompleting(true);
    try {
      await api.post(`/cheat-codes/runs/${runId}/steps/complete`, {
        step_number: 1,
        notes: "Completed step 1",
      });
      // Advance onboarding first_win
      try {
        await api.post("/onboarding/advance?step=first_win");
      } catch {
        // May already be advanced
      }
      setFirstWin(true);
      // Reload run data
      const { data } = await api.get(`/cheat-codes/runs/${runId}`);
      setRun(data);
    } catch (err) {
      if (isApiError(err)) {
        setError(err.message);
        setRequestId(err.requestId);
      }
    } finally {
      setCompleting(false);
    }
  }

  if (loading) return <div className="flex items-center justify-center min-h-screen">Loading...</div>;

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 data-testid={TID.runTitle} className="text-2xl font-bold mb-4">{title}</h1>

      <ErrorBox message={error} requestId={requestId} />

      {firstWin && (
        <div
          data-testid={TID.firstWinBanner}
          className="bg-green-100 border border-green-300 rounded p-4 mb-6 text-green-800 font-semibold"
        >
          First Win achieved!
        </div>
      )}

      {run && (
        <>
          <p data-testid={TID.runStatus} className="text-sm text-gray-600 mb-4">
            Status: {run.status} | Steps: {run.completed_steps}/{run.total_steps}
          </p>

          <div data-testid={TID.runSteps} className="space-y-2 mb-6">
            {Array.from({ length: run.total_steps }, (_, i) => {
              const stepData = run.steps?.[i];
              const completed = i < run.completed_steps;
              return (
                <div
                  key={i}
                  data-testid={TID.runStep}
                  className={`border rounded p-3 ${completed ? "bg-green-50" : "bg-white"}`}
                >
                  <span data-testid={TID.runStepTitle} className="font-medium">
                    Step {i + 1}{stepData?.title ? `: ${stepData.title}` : ""}
                  </span>
                  <span data-testid={TID.runStepStatus} className="ml-2 text-xs text-gray-500">
                    {completed ? "completed" : "pending"}
                  </span>
                </div>
              );
            })}
          </div>

          {run.completed_steps === 0 && !firstWin && (
            <button
              data-testid={TID.runCompleteStep1}
              onClick={completeStep1}
              disabled={completing}
              className="bg-blue-600 text-white rounded px-6 py-2 disabled:opacity-50"
            >
              {completing ? "Completing..." : "Complete step 1"}
            </button>
          )}

          {firstWin && (
            <button
              onClick={() => router.push("/home")}
              className="bg-green-600 text-white rounded px-6 py-2 mt-4"
            >
              Go to Home
            </button>
          )}
        </>
      )}
    </div>
  );
}
