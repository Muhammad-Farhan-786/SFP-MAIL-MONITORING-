import { afterEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import AlertSettings from "./AlertSettings";
import { api } from "./api";
vi.mock("./api", () => ({
  api: vi.fn(),
  when: (v: string | null) => v || "Never sent",
}));
const policy = {
  enabled: true,
  paused: false,
  recipients: ["team@example.com"],
  reminder_seconds: 300,
  critical_only: false,
};
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function setup() {
  vi.mocked(api).mockImplementation(async (path, options) =>
    options?.method === "PUT"
      ? JSON.parse(String(options.body))
      : {
          settings: policy,
          last_sent: null,
          last_delivery_status: "Never Sent",
          history: [],
        },
  );
  const save = vi.fn((fn: () => Promise<unknown>) => {
    void fn();
  });
  render(<AlertSettings domainId={1} busy={false} save={save} />);
  return save;
}
describe("alert controls", () => {
  it("saves pause and keeps monitoring separate", async () => {
    setup();
    fireEvent.click(
      await screen.findByRole("button", { name: "Pause alerts" }),
    );
    await waitFor(() =>
      expect(
        vi
          .mocked(api)
          .mock.calls.some(
            ([p, o]) =>
              p.endsWith("/settings") && JSON.parse(String(o?.body)).paused,
          ),
      ).toBe(true),
    );
  });
  it("preserves comma-separated recipient editing until save", async () => {
    setup();
    const input = await screen.findByLabelText("Alert recipients");
    fireEvent.change(input, {
      target: { value: "first@example.com, second@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save alert settings" }),
    );
    await waitFor(() => {
      const call = vi
        .mocked(api)
        .mock.calls.find(([p]) => p.endsWith("/settings"));
      expect(JSON.parse(String(call?.[1]?.body)).recipients).toEqual([
        "first@example.com",
        "second@example.com",
      ]);
    });
  });
  it("clearly shows untested delivery status", async () => {
    setup();
    expect(await screen.findByText("Never Sent")).toBeVisible();
    expect(screen.queryByText("Sent")).toBeNull();
  });
});
