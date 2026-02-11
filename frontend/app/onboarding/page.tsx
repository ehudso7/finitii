"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api, isApiError, hasToken } from "@/lib/api";
import { TID } from "@/lib/testids";
import { ErrorBox } from "@/components/ErrorBox";
import { buildTransactionPayload } from "@/lib/sample-transactions";

const STEPS = ["Consent", "Account", "Transactions", "Goals", "Top 3"];

interface Rec {
  id: string;
  rank: number;
  confidence: string;
  is_quick_win: boolean;
  explanation: string;
  cheat_code_id: string;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  // Consent
  const [consentData, setConsentData] = useState(false);
  const [consentTerms, setConsentTerms] = useState(false);
  const [consentAi, setConsentAi] = useState(false);

  // Account
  const [institution, setInstitution] = useState("");
  const [acctName, setAcctName] = useState("");
  const [balance, setBalance] = useState("");
  const [accountId, setAccountId] = useState<string | null>(null);

  // Transactions
  const [txnCount, setTxnCount] = useState(0);

  // Goals
  const [goalType, setGoalType] = useState("build_emergency_fund");
  const [constraintLabel, setConstraintLabel] = useState("");
  const [constraints, setConstraints] = useState<string[]>([]);

  // Top 3
  const [recs, setRecs] = useState<Rec[]>([]);

  const clearError = () => { setError(""); setRequestId(null); };

  // Check onboarding state on mount
  useEffect(() => {
    if (!hasToken()) { router.replace("/login"); return; }
    (async () => {
      try {
        const { data } = await api.get("/onboarding/state");
        const s = data.current_step;
        if (s === "completed" || data.first_win_completed_at) {
          router.replace("/home");
          return;
        }
        // Map server step to wizard index
        const map: Record<string, number> = {
          consent: 0, account_link: 1, goals: 2, top_3: 3, first_win: 4,
        };
        // If we're past goals, we need to show Top 3
        if (s in map) {
          // For account_link, show Transactions (step 2 in UI)
          if (s === "account_link") setStep(2);
          else if (s === "goals") setStep(3);
          else if (s === "top_3" || s === "first_win") setStep(4);
          else setStep(map[s] || 0);
        }
      } catch {
        // New user, start at step 0
      } finally {
        setChecking(false);
      }
    })();
  }, [router]);

  const handleError = useCallback((err: unknown) => {
    if (isApiError(err)) {
      setError(err.message);
      setRequestId(err.requestId);
    } else {
      setError("An unexpected error occurred");
    }
  }, []);

  // Step 0: Consent
  async function submitConsent() {
    clearError();
    setLoading(true);
    try {
      if (consentData) await api.post("/consent/grant", { consent_type: "data_access" });
      if (consentTerms) await api.post("/consent/grant", { consent_type: "terms_of_service" });
      if (consentAi) await api.post("/consent/grant", { consent_type: "ai_memory" });
      await api.post("/onboarding/advance?step=consent");
      setStep(1);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  // Step 1: Account
  async function submitAccount() {
    clearError();
    setLoading(true);
    try {
      const { data } = await api.post("/accounts/manual", {
        account_type: "checking",
        institution_name: institution,
        account_name: acctName,
        current_balance: parseFloat(balance) || 0,
        currency: "USD",
      });
      setAccountId(data.id);
      await api.post("/onboarding/advance?step=account_link");
      setStep(2);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  // Step 2: Transactions
  async function addSampleTransactions() {
    clearError();
    setLoading(true);
    try {
      const aid = accountId || (await getFirstAccountId());
      if (!aid) { setError("No account found"); setLoading(false); return; }
      const payloads = buildTransactionPayload(aid);
      let count = 0;
      for (const p of payloads) {
        await api.post("/transactions", p);
        count++;
      }
      setTxnCount(count);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  async function getFirstAccountId(): Promise<string | null> {
    try {
      const { data } = await api.get("/accounts");
      if (Array.isArray(data) && data.length > 0) {
        setAccountId(data[0].id);
        return data[0].id;
      }
    } catch { /* ignore */ }
    return null;
  }

  async function submitTransactions() {
    clearError();
    setLoading(true);
    try {
      // Detect recurring + compute forecast
      await api.post("/recurring/detect");
      await api.post("/forecast/compute");
      setStep(3);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  // Step 3: Goals
  async function addConstraint() {
    if (!constraintLabel.trim()) return;
    clearError();
    try {
      await api.post("/goals/constraints", {
        constraint_type: "essential",
        label: constraintLabel.trim(),
      });
      setConstraints([...constraints, constraintLabel.trim()]);
      setConstraintLabel("");
    } catch (err) { handleError(err); }
  }

  async function submitGoals() {
    clearError();
    setLoading(true);
    try {
      await api.post("/goals", {
        goal_type: goalType,
        title: goalType.replace(/_/g, " "),
        priority: "high",
      });
      await api.post("/onboarding/advance?step=goals");
      // Fetch Top 3
      const { data } = await api.post("/cheat-codes/top-3");
      setRecs(Array.isArray(data) ? data : []);
      await api.post("/onboarding/advance?step=top_3");
      setStep(4);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  // Step 4: Top 3 — Start a run
  async function startRun(recId: string) {
    clearError();
    setLoading(true);
    try {
      const { data } = await api.post("/cheat-codes/runs", { recommendation_id: recId });
      router.push(`/cheat/run/${data.id}`);
    } catch (err) { handleError(err); }
    finally { setLoading(false); }
  }

  if (checking) return <div className="flex items-center justify-center min-h-screen">Loading...</div>;

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 data-testid={TID.onboardingTitle} className="text-2xl font-bold mb-6">Onboarding</h1>

      {/* Stepper */}
      <div data-testid={TID.onboardingStepper} className="flex gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div
            key={s}
            data-testid={TID.onboardingStepLabel}
            className={`px-3 py-1 rounded text-sm ${i === step ? "bg-blue-600 text-white" : i < step ? "bg-green-100 text-green-800" : "bg-gray-200 text-gray-500"}`}
          >
            {s}
          </div>
        ))}
      </div>

      <ErrorBox message={error} requestId={requestId} />

      {/* Step 0: Consent */}
      {step === 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Consent</h2>
          <label className="flex items-center gap-2">
            <input
              data-testid={TID.consentDataAccess}
              type="checkbox"
              name="consent_data_access"
              checked={consentData}
              onChange={(e) => setConsentData(e.target.checked)}
            />
            Data Access
          </label>
          <label className="flex items-center gap-2">
            <input
              data-testid={TID.consentTerms}
              type="checkbox"
              name="consent_terms_of_service"
              checked={consentTerms}
              onChange={(e) => setConsentTerms(e.target.checked)}
            />
            Terms of Service
          </label>
          <label className="flex items-center gap-2">
            <input
              data-testid={TID.consentAiMemory}
              type="checkbox"
              name="consent_ai_memory"
              checked={consentAi}
              onChange={(e) => setConsentAi(e.target.checked)}
            />
            AI Memory (optional)
          </label>
          <button
            data-testid={TID.onboardingContinue}
            onClick={submitConsent}
            disabled={!consentData || !consentTerms || loading}
            className="bg-blue-600 text-white rounded px-6 py-2 disabled:opacity-50"
          >
            {loading ? "..." : "Continue"}
          </button>
        </div>
      )}

      {/* Step 1: Account */}
      {step === 1 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Add Account</h2>
          <input
            data-testid={TID.accountInstitution}
            name="institution_name"
            placeholder="Institution name"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            className="w-full border rounded p-2"
          />
          <input
            data-testid={TID.accountName}
            name="account_name"
            placeholder="Account name"
            value={acctName}
            onChange={(e) => setAcctName(e.target.value)}
            className="w-full border rounded p-2"
          />
          <input
            data-testid={TID.accountBalance}
            name="current_balance"
            type="number"
            placeholder="Current balance"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            className="w-full border rounded p-2"
          />
          <button
            data-testid={TID.onboardingContinue}
            onClick={submitAccount}
            disabled={!institution || !acctName || loading}
            className="bg-blue-600 text-white rounded px-6 py-2 disabled:opacity-50"
          >
            {loading ? "..." : "Continue"}
          </button>
        </div>
      )}

      {/* Step 2: Transactions */}
      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Add Transactions</h2>
          <button
            data-testid={TID.txnsAddSample}
            onClick={addSampleTransactions}
            disabled={loading}
            className="bg-gray-200 rounded px-4 py-2 hover:bg-gray-300 disabled:opacity-50"
          >
            {loading ? "Adding..." : "Add sample transactions"}
          </button>
          {txnCount > 0 && (
            <p data-testid={TID.txnsCount} className="text-sm text-green-700">
              {txnCount} transactions added
            </p>
          )}
          <button
            data-testid={TID.onboardingContinue}
            onClick={submitTransactions}
            disabled={txnCount === 0 || loading}
            className="bg-blue-600 text-white rounded px-6 py-2 disabled:opacity-50"
          >
            {loading ? "..." : "Continue"}
          </button>
        </div>
      )}

      {/* Step 3: Goals */}
      {step === 3 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Set a Goal</h2>
          <select
            data-testid={TID.goalType}
            name="goal_type"
            value={goalType}
            onChange={(e) => setGoalType(e.target.value)}
            className="w-full border rounded p-2"
          >
            <option value="build_emergency_fund">Build emergency fund</option>
            <option value="build_buffer">Build buffer</option>
            <option value="save_money">Save money</option>
            <option value="reduce_spending">Reduce spending</option>
            <option value="pay_off_debt">Pay off debt</option>
            <option value="budget_better">Budget better</option>
          </select>
          <div className="flex gap-2">
            <input
              data-testid={TID.constraintLabel}
              name="constraint_label"
              placeholder="Add a constraint (optional)"
              value={constraintLabel}
              onChange={(e) => setConstraintLabel(e.target.value)}
              className="flex-1 border rounded p-2"
            />
            <button
              data-testid={TID.constraintAdd}
              onClick={addConstraint}
              className="bg-gray-200 rounded px-4 py-2 hover:bg-gray-300"
            >
              Add constraint
            </button>
          </div>
          {constraints.length > 0 && (
            <ul className="text-sm text-gray-600">
              {constraints.map((c, i) => <li key={i}>- {c}</li>)}
            </ul>
          )}
          <button
            data-testid={TID.onboardingContinue}
            onClick={submitGoals}
            disabled={loading}
            className="bg-blue-600 text-white rounded px-6 py-2 disabled:opacity-50"
          >
            {loading ? "..." : "Continue"}
          </button>
        </div>
      )}

      {/* Step 4: Top 3 */}
      {step === 4 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Your Top 3 Moves</h2>
          <div data-testid={TID.top3List} className="space-y-4">
            {recs.map((rec) => (
              <div
                key={rec.id}
                data-testid={TID.top3Card}
                className="border rounded p-4 bg-white shadow-sm"
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
                <p className="text-sm mb-2">{rec.explanation}</p>
                <div className="flex gap-2">
                  <button
                    data-testid={TID.top3Start}
                    onClick={() => startRun(rec.id)}
                    disabled={loading}
                    className="bg-blue-600 text-white rounded px-4 py-1 text-sm disabled:opacity-50"
                  >
                    Start
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
