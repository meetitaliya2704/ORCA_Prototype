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
  expect(screen.getByRole("heading", { name: "PFZ journey and evidence" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Mock marine map")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View on map" })).not.toBeInTheDocument();
});

test("disabled free-text response remains visible after suggestions collapse", async () => {
  const user = userEvent.setup();
  renderDashboard();

  await user.type(screen.getByLabelText("Message Ask ORCA"), "huhu{enter}");

  const history = screen.getByRole("log", { name: "ORCA conversation" });
  expect(within(history).getByText("huhu")).toBeVisible();
  expect(await within(history).findByText(/Conversational agent connection is not enabled/i)).toBeVisible();
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: /Where is the nearest PFZ today\?/ })).not.toBeInTheDocument();
});

test("deterministic quick action reveals advanced parameters and clarification", async () => {
  const user = userEvent.setup();
  renderDashboard();
  expect(screen.getByRole("button", { name: /Advanced query parameters/i, expanded: false })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Where is the nearest PFZ today\?/ }));
  expect(screen.getByRole("button", { name: /Advanced query parameters/i, expanded: true })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "PFZ journey query" })).toBeInTheDocument();
  expect(screen.getByText(/Add your location and at least one user-supplied operational limit/i)).toBeInTheDocument();
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

test("planned warning question is labelled and does not open a map", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await user.click(screen.getByRole("button", { name: /Are official cyclone or lightning alerts available\?/ }));
  expect(screen.getByText(/Planned capability: authorized cyclone and lightning warning integrations are not available/i)).toBeInTheDocument();
  expect(screen.queryByLabelText("Mock marine map")).not.toBeInTheDocument();
});

test("advanced form validation produces a conversation clarification without losing fields", async () => {
  const user = userEvent.setup();
  renderDashboard();
  await user.click(screen.getByRole("button", { name: /Advanced query parameters/i, expanded: false }));
  await user.type(screen.getByLabelText(/Latitude/), "91");
  await user.click(screen.getByRole("button", { name: "Find nearest PFZ" }));
  expect(screen.getByLabelText(/Latitude/)).toHaveValue("91");
  expect(screen.getAllByText(/Add your location and at least one user-supplied operational limit/i).length).toBeGreaterThan(0);
});
