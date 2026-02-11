"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, isApiError, hasToken } from "@/lib/api";
import { TID } from "@/lib/testids";
import { ErrorBox } from "@/components/ErrorBox";

interface Forecast {
  safe_to_spend_today: string;
  safe_to_spend_week: string;
  confidence: string;
  assumptions: string[];
  urgency_score: number;
}

interface Rec {
  id: string;
  rank: number;
  confidence: string;
  is_quick_win: boolean;
  explanation: string;
}

export default function HomePage() {
  const router = useRouter();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [recs, setRecs] = useState<Rec[]>([]);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hasToken()) { router.replace("/login"); return; }
    checkOnboardingAndLoad();
  }, [router]);

  async function checkOnboardingAndLoad() {
    try {
      // Check onboarding state — redirect if not complete
      const { data: state } = await api.get("/onboarding/state");
      if (!state.first_win_completed_at && state.current_step !== "completed") {
        router.replace("/onboarding");
        return;
      }

      // Load forecast
      try {
        const { data: fc } = await api.get("/forecast/latest");
        setForecast(fc);
      } catch {
        // No forecast yet
      }

      // Load top 3
      try {
        const { data: r } = await api.get("/cheat-codes/recommendations");
        setRecs(Array.isArray(r) ? r : []);
      } catch {
        // No recommendations yet
      }
    } catch (err) {
      if (isApiError(err)) {
        if (err.status === 401) { router.replace("/login"); return; }
        setError(err.message);
        setRequestId(err.requestId);
      }
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="flex items-center justify-center min-h-screen">Loading...</div>;

  return (
    <div className="max-w-3xl mx-auto p-8">
      {/* Nav */}
      <nav className="flex gap-4 mb-8 border-b pb-4">
        <Link href="/home" data-testid={TID.navHome} className="font-semibold text-blue-600">Home</Link>
        <Link href="/settings" data-testid={TID.navSettings} className="text-gray-600 hover:text-gray-900">Settings</Link>
      </nav>

      <ErrorBox message={error} requestId={requestId} />

      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Forecast */}
      {forecast && (
        <div className="bg-white rounded shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Safe to Spend</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p className="text-sm text-gray-500">Today</p>
              <p data-testid={TID.stsToday} className="text-2xl font-bold">
                ${parseFloat(forecast.safe_to_spend_today).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">This Week</p>
              <p data-testid={TID.stsWeek} className="text-2xl font-bold">
                ${parseFloat(forecast.safe_to_spend_week).toFixed(2)}
              </p>
            </div>
          </div>
          <p data-testid={TID.forecastConfidence} className="text-sm text-gray-600 mb-2">
            Confidence: {forecast.confidence}
          </p>
          <button
            data-testid={TID.assumptionsOpen}
            onClick={() => setShowAssumptions(!showAssumptions)}
            className="text-sm text-blue-600 underline"
          >
            {showAssumptions ? "Hide assumptions" : "Show assumptions"}
          </button>
          {showAssumptions && (
            <div data-testid={TID.assumptionsDrawer} className="mt-2 p-3 bg-gray-50 rounded text-sm">
              <ul className="list-disc list-inside">
                {forecast.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Top 3 */}
      {recs.length > 0 && (
        <div className="bg-white rounded shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Top 3 Moves</h2>
          <div data-testid={TID.top3List} className="space-y-4">
            {recs.map((rec) => (
              <div
                key={rec.id}
                data-testid={TID.top3Card}
                className="border rounded p-4"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span
                    data-testid={TID.top3Confidence}
                    className={`text-xs px-2 py-0.5 rounded ${rec.confidence === "high" ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"}`}
                  >
                    {rec.confidence}
                  </span>
                  {rec.is_quick_win && (
                    <span data-testid={TID.top3Quickwin} className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                      Quick Win
                    </span>
                  )}
                </div>
                <p className="text-sm">{rec.explanation}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
