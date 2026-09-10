import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/use-health", () => ({ useBackendHealth: () => ({ isSuccess: true, isError: false }) }));
vi.mock("@/hooks/use-journey", () => ({
  useJourney: () => ({ result: null, mode: "live", pending: false, error: null, isSubmitting: false,
    submit: vi.fn(), retry: vi.fn(), cancel: vi.fn(), loadDemo: vi.fn() }),
}));
vi.mock("@/components/map/map-panel", () => ({ MapPanel: () => <div aria-label="Mock marine map">Map</div> }));

import { OrcaDashboard } from "@/components/dashboard/orca-dashboard";
import { SpatialMapDialog } from "@/components/map/spatial-map-dialog";
import journeyFixture from "@/public/demo/pfz-journey.json";
import { journeyResponseSchema } from "@/lib/schemas/journey";

function renderDashboard() {
  return render(<QueryClientProvider client={new QueryClient()}><OrcaDashboard /></QueryClientProvider>);
}

test("dashboard is useful without loading the optional MapLibre panel", async () => {
  const user = userEvent.setup();
  renderDashboard();
  const composer = screen.getByLabelText("Message Ask ORCA");
  await user.type(composer, "preserved question");
  expect(composer).toHaveValue("preserved question");
  expect(screen.getByRole("heading", { name: "Evidence-backed answers appear here" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Mock marine map")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View on map" })).not.toBeInTheDocument();
}, 15000);

test("suggested questions and the complete assistant query context are visible initially", () => {
  renderDashboard();
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("button", { name: /Find nearest PFZ advisory/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Check marine conditions/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Assess operational limits/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Explain evidence sources/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Query context/i })).toHaveAttribute("aria-expanded", "true");
  for (const fieldId of ["latitude", "longitude", "requestedTimeLocal", "waveLimit", "windLimit", "currentLimit"]) {
    expect(document.getElementById(`assistant-${fieldId}`)).toBeVisible();
  }
});

test("disabled free-text response remains visible after suggestions collapse", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.type(screen.getByLabelText("Message Ask ORCA"), "huhu{enter}");

  const history = screen.getByRole("log", { name: "ORCA conversation" });
  expect(within(history).getByText("huhu")).toBeVisible();
  expect(await within(history).findByText(/The assistant request|too long|initializing|could not be reached|I can assist/i)).toBeVisible();
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: /Find nearest PFZ advisory/ })).not.toBeInTheDocument();
});

test("quick action triggers assistant message in live mode", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await user.click(screen.getByRole("button", { name: /Find nearest PFZ advisory/ }));
  const history = screen.getByRole("log", { name: "ORCA conversation" });
  expect(within(history).getByText("Find nearest PFZ advisory")).toBeVisible();
});

test("MapLibre is lazy and closing its accessible dialog preserves surrounding state", async () => {
  const user = userEvent.setup();
  const result = journeyResponseSchema.parse(journeyFixture);
  render(<><label htmlFor="preserved">Question</label><input id="preserved" defaultValue="keep this" /><SpatialMapDialog result={result} /></>);
  expect(screen.queryByLabelText("Mock marine map")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "View on map" }));
  expect(await screen.findByLabelText("Mock marine map")).toBeInTheDocument();
  expect(screen.getByText(/Supporting spatial visualization/)).toBeInTheDocument();
  expect(screen.getByText(/Reference line — route not evaluated/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Close map" }));
  expect(screen.getByLabelText("Question")).toHaveValue("keep this");
});

test("assistant-first dashboard keeps map optional before a spatial result", () => {
  renderDashboard();
  expect(screen.queryByLabelText("Mock marine map")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View on map" })).not.toBeInTheDocument();
});

test("advanced form validation produces a conversation clarification without losing fields", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await user.click(screen.getByRole("button", { name: /Advanced query parameters/i, expanded: false }));
  const latitude = document.getElementById("latitude") as HTMLInputElement;
  await user.type(latitude, "91");
  await user.click(screen.getByRole("button", { name: "Find nearest PFZ" }));
  expect(latitude).toHaveValue("91");
  expect(screen.getAllByText(/Add the missing query context/i).length).toBeGreaterThan(0);
});
