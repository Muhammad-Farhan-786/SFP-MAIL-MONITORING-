import { test, expect } from "@playwright/test";
const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
test.beforeEach(async ({ page }) => {
  if (!email || !password)
    throw new Error(
      "Set E2E_EMAIL and E2E_PASSWORD through your secure environment",
    );
  await page.goto("./");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in to dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Email overview" }),
  ).toBeVisible();
});
test("desktop navigation, unknown data, score details and console", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await expect(
    page.getByText("Delivery success", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/email-health-overview.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Explain health score" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("Measurement coverage:", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close details" }).click();
  for (const name of [
    "Authentication",
    "Deliverability",
    "Inbox Placement",
    "Reputation",
    "Issues",
    "Reports",
    "Monitoring History",
    "Settings",
    "System Status",
  ]) {
    await page
      .getByRole("navigation")
      .getByRole("button", { name, exact: true })
      .click();
    await expect(
      page.getByRole("heading", { level: 1, name, exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  await page.screenshot({
    path: "/tmp/email-health-desktop.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
test("mobile navigation and no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Issues", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Issues", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/email-health-mobile.png",
    fullPage: true,
  });
});
