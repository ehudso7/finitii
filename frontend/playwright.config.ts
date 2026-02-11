import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.WEB_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    launchOptions: {
      executablePath:
        "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome",
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--headless=new",
        "--no-zygote",
      ],
    },
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
