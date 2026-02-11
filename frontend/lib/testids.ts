/**
 * Frozen data-testid contract for Phase 10 Playwright E2E tests.
 * DO NOT CHANGE THESE IDs — tests depend on them.
 */
export const TID = {
  // Auth
  authEmail: "auth-email",
  authPassword: "auth-password",
  authSubmit: "auth-submit",
  authToLogin: "auth-to-login",
  authToRegister: "auth-to-register",

  // Global error
  errorBox: "error-box",
  requestId: "request-id",
  errorMessage: "error-message",

  // Onboarding
  onboardingTitle: "onboarding-title",
  onboardingStepper: "onboarding-stepper",
  onboardingStepLabel: "onboarding-step-label",
  onboardingContinue: "onboarding-continue",

  // Consent step
  consentDataAccess: "consent-data-access",
  consentTerms: "consent-terms",
  consentAiMemory: "consent-ai-memory",

  // Account step
  accountInstitution: "account-institution",
  accountName: "account-name",
  accountBalance: "account-balance",
  accountCurrency: "account-currency",

  // Transactions step
  txnsAddSample: "txns-add-sample",
  txnsCsvUpload: "txns-csv-upload",
  txnsCount: "txns-count",

  // Goals step
  goalType: "goal-type",
  constraintLabel: "constraint-label",
  constraintAdd: "constraint-add",

  // Top 3
  top3List: "top3-list",
  top3Card: "top3-card",
  top3Confidence: "top3-confidence",
  top3Quickwin: "top3-quickwin",
  top3Why: "top3-why",
  top3Start: "top3-start",

  // Home / Nav
  navHome: "nav-home",
  navSettings: "nav-settings",
  stsToday: "sts-today",
  stsWeek: "sts-week",
  forecastConfidence: "forecast-confidence",
  assumptionsOpen: "assumptions-open",
  assumptionsDrawer: "assumptions-drawer",

  // Run page
  runTitle: "run-title",
  runStatus: "run-status",
  runSteps: "run-steps",
  runStep: "run-step",
  runStepTitle: "run-step-title",
  runStepStatus: "run-step-status",
  runCompleteStep1: "run-complete-step-1",
  firstWinBanner: "first-win-banner",

  // Settings
  settingsExport: "settings-export",
  settingsExportDownload: "settings-export-download",
  settingsDelete: "settings-delete",
  settingsDeleteConfirm: "settings-delete-confirm",
} as const;
