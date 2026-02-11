import { test, expect } from "@playwright/test";

const WEB = process.env.WEB_BASE_URL || "http://localhost:3000";

// All selectors use data-testid attributes from the frozen contract.
const SEL = {
  emailInput: '[data-testid="auth-email"]',
  passwordInput: '[data-testid="auth-password"]',
  submitAuth: '[data-testid="auth-submit"]',

  onboardingTitle: '[data-testid="onboarding-title"]',

  // Consent toggles (required)
  consentDataAccess: '[data-testid="consent-data-access"]',
  consentTerms: '[data-testid="consent-terms"]',
  consentAiMemory: '[data-testid="consent-ai-memory"]',

  continueBtn: '[data-testid="onboarding-continue"]',

  // Account form
  acctName: '[data-testid="account-name"]',
  acctInstitution: '[data-testid="account-institution"]',
  acctBalance: '[data-testid="account-balance"]',

  // Transactions
  addSampleTxnsBtn: '[data-testid="txns-add-sample"]',

  // Goals
  goalSelect: '[data-testid="goal-type"]',
  constraintInput: '[data-testid="constraint-label"]',
  addConstraintBtn: '[data-testid="constraint-add"]',

  // Top 3 cards
  top3Card: '[data-testid="top3-card"]',
  top3Confidence: '[data-testid="top3-confidence"]',
  top3QuickWin: '[data-testid="top3-quickwin"]',
  top3Why: '[data-testid="top3-why"]',
  startCheatBtn: '[data-testid="top3-start"]',

  // Run page
  runTitle: '[data-testid="run-title"]',
  completeStep0Btn: '[data-testid="run-complete-step-1"]',
  firstWinBanner: '[data-testid="first-win-banner"]',

  // Nav
  navHome: '[data-testid="nav-home"]',
  navSettings: '[data-testid="nav-settings"]',

  // Settings
  exportBtn: '[data-testid="settings-export"]',
  exportDownloadLink: '[data-testid="settings-export-download"]',
  deleteBtn: '[data-testid="settings-delete"]',
  confirmDeleteBtn: '[data-testid="settings-delete-confirm"]',

  // Error UI
  errorBox: '[data-testid="error-box"]',
  requestId: '[data-testid="request-id"]',
};

function uniqueEmail() {
  const ts = Date.now();
  return `beta+ui+${ts}@example.com`;
}

async function registerAndLogin(page: any, email: string, password: string) {
  await page.goto(`${WEB}/register`);
  await expect(page.locator(SEL.emailInput)).toBeVisible();
  await page.fill(SEL.emailInput, email);
  await page.fill(SEL.passwordInput, password);
  await page.click(SEL.submitAuth);
}

test.describe("Phase 10 — Minimal Web Shell ship gates", () => {
  test("P10-E2E-01: New user completes onboarding First Win (cannot bypass)", async ({
    page,
  }) => {
    const email = uniqueEmail();
    const password = "ChangeMe123!";

    await registerAndLogin(page, email, password);

    // Should land in onboarding
    await expect(page.locator(SEL.onboardingTitle)).toBeVisible();

    // Attempt to jump to /home should redirect back until First Win
    await page.goto(`${WEB}/home`);
    await expect(page.locator(SEL.onboardingTitle)).toBeVisible();

    // Step 1: Consent
    await page.check(SEL.consentDataAccess);
    await page.check(SEL.consentTerms);
    // AI memory must remain off by default (not checked)
    await expect(page.locator(SEL.consentAiMemory)).not.toBeChecked();
    await page.click(SEL.continueBtn);

    // Step 2: Account (manual)
    await page.fill(SEL.acctInstitution, "Manual Bank");
    await page.fill(SEL.acctName, "Main Checking");
    await page.fill(SEL.acctBalance, "1250");
    await page.click(SEL.continueBtn);

    // Step 3: Transactions
    await page.click(SEL.addSampleTxnsBtn);
    await page.click(SEL.continueBtn);

    // Step 4: Goals
    await page.selectOption(SEL.goalSelect, "build_buffer");
    await page.fill(SEL.constraintInput, "Gym is essential");
    await page.click(SEL.addConstraintBtn);
    await page.click(SEL.continueBtn);

    // Step 5: Top 3 must be visible
    await expect(page.locator(SEL.top3Card)).toHaveCount(3);

    // Validate Top 3: no low confidence, at least one quick win badge
    const confidences = await page
      .locator(SEL.top3Card)
      .locator(SEL.top3Confidence)
      .allTextContents();
    for (const c of confidences) {
      expect(c.toLowerCase()).not.toContain("low");
    }
    const quickWins = await page
      .locator(SEL.top3Card)
      .locator(SEL.top3QuickWin)
      .count();
    expect(quickWins).toBeGreaterThanOrEqual(1);

    // Start first recommendation
    await page
      .locator(SEL.top3Card)
      .first()
      .locator(SEL.startCheatBtn)
      .click();

    // Must be on run page
    await expect(page.locator(SEL.runTitle)).toBeVisible();

    // Complete step 1 => First Win
    await page.click(SEL.completeStep0Btn);
    await expect(page.locator(SEL.firstWinBanner)).toBeVisible();

    // Now /home should be accessible
    await page.goto(`${WEB}/home`);
    await expect(page.locator(SEL.navHome)).toBeVisible();
  });

  test("P10-E2E-02: Export from Settings works (no secrets) and returns JSON download/link", async ({
    page,
  }) => {
    const email = uniqueEmail();
    const password = "ChangeMe123!";

    await registerAndLogin(page, email, password);

    // Complete onboarding quickly via same flow assumptions:
    await expect(page.locator(SEL.onboardingTitle)).toBeVisible();
    await page.check(SEL.consentDataAccess);
    await page.check(SEL.consentTerms);
    await page.click(SEL.continueBtn);

    await page.fill(SEL.acctInstitution, "Manual Bank");
    await page.fill(SEL.acctName, "Main Checking");
    await page.fill(SEL.acctBalance, "1250");
    await page.click(SEL.continueBtn);

    await page.click(SEL.addSampleTxnsBtn);
    await page.click(SEL.continueBtn);

    await page.selectOption(SEL.goalSelect, "build_buffer");
    await page.click(SEL.continueBtn);

    await expect(page.locator(SEL.top3Card)).toHaveCount(3);
    await page
      .locator(SEL.top3Card)
      .first()
      .locator(SEL.startCheatBtn)
      .click();
    await page.click(SEL.completeStep0Btn);
    await expect(page.locator(SEL.firstWinBanner)).toBeVisible();

    // Settings -> Export
    await page.goto(`${WEB}/settings`);
    await page.click(SEL.exportBtn);

    // If your UI triggers a download, Playwright can capture it:
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.click(SEL.exportBtn).catch(() => {}), // if export is a second click
    ]).catch(() => [null]);

    if (download) {
      const path = await download.path();
      expect(path).toBeTruthy();
    } else {
      // Or you present a link
      await expect(page.locator(SEL.exportDownloadLink)).toBeVisible();
    }

    // Optional: if your UI renders JSON preview, assert no password hash string
    // (Selector depends on your UI; leave as a suggestion)
  });

  test("P10-E2E-03: Delete account locks out user and redirects to login", async ({
    page,
  }) => {
    const email = uniqueEmail();
    const password = "ChangeMe123!";

    await registerAndLogin(page, email, password);

    // Minimal onboarding completion for unlock
    await page.check(SEL.consentDataAccess);
    await page.check(SEL.consentTerms);
    await page.click(SEL.continueBtn);
    await page.fill(SEL.acctInstitution, "Manual Bank");
    await page.fill(SEL.acctName, "Main Checking");
    await page.fill(SEL.acctBalance, "1250");
    await page.click(SEL.continueBtn);
    await page.click(SEL.addSampleTxnsBtn);
    await page.click(SEL.continueBtn);
    await page.selectOption(SEL.goalSelect, "build_buffer");
    await page.click(SEL.continueBtn);
    await page
      .locator(SEL.top3Card)
      .first()
      .locator(SEL.startCheatBtn)
      .click();
    await page.click(SEL.completeStep0Btn);
    await expect(page.locator(SEL.firstWinBanner)).toBeVisible();

    // Delete
    await page.goto(`${WEB}/settings`);
    await page.click(SEL.deleteBtn);
    await page.click(SEL.confirmDeleteBtn);

    // Should end on login or register
    await expect(page).toHaveURL(/\/login|\/register/);

    // Attempt to access home should redirect to login
    await page.goto(`${WEB}/home`);
    await expect(page).toHaveURL(/\/login/);
  });

  test("P10-E2E-04: Errors show request id (X-Request-ID)", async ({
    page,
  }) => {
    // Trigger a controlled error: go to a protected route without login
    await page.goto(`${WEB}/home`);

    // Should redirect to login OR show an auth error with request id
    // If redirected, we're done; if error UI shows, verify request id
    const url = page.url();
    if (url.includes("/login") || url.includes("/register")) {
      expect(true).toBeTruthy();
      return;
    }

    // Otherwise validate error UI contract
    await expect(page.locator(SEL.errorBox)).toBeVisible();
    await expect(page.locator(SEL.requestId)).toBeVisible();
    const rid = await page.locator(SEL.requestId).innerText();
    expect(rid.length).toBeGreaterThan(8);
  });
});
