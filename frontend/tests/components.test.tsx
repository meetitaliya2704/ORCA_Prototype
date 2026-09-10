import demo from "@/public/demo/pfz-journey.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvidenceCard } from "@/components/evidence/evidence-card";
import { JourneyForm } from "@/components/journey/journey-form";
import { JourneyPanel } from "@/components/journey/journey-panel";
import { SourceDrawer } from "@/components/evidence/source-drawer";
import MarineMap, { fitJourneyGeoJson } from "@/components/map/marine-map";
import { journeyResponseSchema } from "@/lib/schemas/journey";

const result = journeyResponseSchema.parse(demo);

test("journey success renders PFZ and controlled backend terminology", () => {
  render(<JourneyPanel result={result} demonstration={false} />);
  expect(screen.getByText("Demonstration Landing Centre")).toBeInTheDocument();
  expect(screen.getByText(/PFZ AVAILABLE CAUTION/i)).toBeInTheDocument();
  expect(screen.queryByText(/^safe$/i)).not.toBeInTheDocument();
});

test("journey panel renders clean landing centre and status", () => {
  render(<JourneyPanel result={result} demonstration />);
  expect(screen.getByText("Demonstration Landing Centre")).toBeInTheDocument();
});

test("limit exceeded never renders safe wording", () => {
  render(<JourneyPanel result={{ ...result, journey_status: "PFZ_AVAILABLE_LIMIT_EXCEEDED" }} demonstration={false} />);
  expect(screen.getByText(/LIMIT EXCEEDED/i)).toBeInTheDocument();
  expect(screen.queryByText(/safe route/i)).not.toBeInTheDocument();
});

test("wind card preserves direction-from semantics", () => {
  render(<EvidenceCard source="wind" item={result.origin.evidence!.evidence.wind} />);
  expect(screen.getByText("direction-from:")).toBeInTheDocument();
});

test("current card preserves direction-toward semantics", () => {
  render(<EvidenceCard source="currents" item={result.origin.evidence!.evidence.currents} />);
  expect(screen.getByText("direction-toward:")).toBeInTheDocument();
});

test("degraded chlorophyll is textual and does not imply success", () => {
  render(<EvidenceCard source="chlorophyll" item={result.origin.evidence!.evidence.chlorophyll} />);
  expect(screen.getByText("degraded")).toBeInTheDocument();
  expect(screen.queryByText(/fish present/i)).not.toBeInTheDocument();
});

test("live chlorophyll value and nested uncertainty are rendered", async () => {
  const user = userEvent.setup();
  const item = structuredClone(result.origin.evidence!.evidence.chlorophyll);
  item.data = {
    ...item.data,
    chlorophyll_a: { value: 1.12, unit: "mg/m³" },
    quality: {
      flag_value: 4,
      land: false,
      interpolated: true,
      uncertainty_percent: 54,
      evidence_quality: "degraded",
    },
  };
  render(<EvidenceCard source="chlorophyll" item={item} />);
  expect(screen.getByText(/1\.12/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Source details" }));
  expect(screen.getByText(/54%/)).toBeInTheDocument();
});

test("form controls are keyboard accessible and retain invalid values", async () => {
  const user = userEvent.setup();
  render(<JourneyForm onSubmit={vi.fn()} onDemo={vi.fn()} onCancel={vi.fn()} submitting={false} demoEnabled={false} />);
  const latitude = screen.getByLabelText(/Latitude/);
  await user.type(latitude, "91");
  await user.click(screen.getByRole("button", { name: "Find nearest PFZ" }));
  expect(latitude).toHaveValue("91");
  expect(screen.getAllByRole("alert")[0]).toHaveTextContent("Enter a latitude from -90 to 90");
});

test("source drawer exposes required disclaimer", async () => {
  const user = userEvent.setup();
  render(<SourceDrawer result={result} />);
  await user.click(screen.getByRole("button", { name: /Sources and provenance/i }));
  expect(screen.getByText(/Verify authority-issued advisories/i)).toBeInTheDocument();
});

test("responsive dashboard regions use semantic headings without raw JSON", () => {
  render(<><JourneyForm onSubmit={vi.fn()} onDemo={vi.fn()} onCancel={vi.fn()} submitting={false} demoEnabled={false} /><JourneyPanel result={null} demonstration={false} /></>);
  expect(screen.getByRole("heading", { name: "PFZ journey query" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "PFZ journey and evidence" })).toBeInTheDocument();
  expect(screen.queryByText(/\{"request"/)).not.toBeInTheDocument();
});

test("no-valid-PFZ and insufficient-evidence outcomes remain explicit", () => {
  const noPfz = {
    ...result,
    journey_status: "NO_VALID_PFZ" as const,
    pfz_resolution: { status: "NO_VALID_PFZ" as const, failure: { code: "NO_VALID_PFZ", message: "No valid PFZ", retryable: false } },
    pfz: null,
    destination: null,
    distance: null,
    geojson: null,
  };
  const { rerender } = render(<JourneyPanel result={noPfz} demonstration={false} />);
  expect(screen.getAllByText(/NO VALID PFZ/i)[0]).toBeInTheDocument();
  rerender(<JourneyPanel result={{ ...result, journey_status: "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE" }} demonstration={false} />);
  expect(screen.getByText(/INSUFFICIENT EVIDENCE/i)).toBeInTheDocument();
});

test("partial and pending evidence states remain visible", () => {
  render(<EvidenceCard source="sst" item={{ state: "pending", data: null }} />);
  expect(screen.getByText("pending")).toBeInTheDocument();
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
});

test("map failure preserves the non-navigational reference-line label", () => {
  render(<MarineMap result={result} />);
  expect(screen.getByText("Reference line — route not evaluated")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Map unavailable");
});

test("journey GeoJSON fits the camera to the two official point coordinates", () => {
  const fitBounds = vi.fn();
  const instance = { fitBounds } as unknown as Parameters<typeof fitJourneyGeoJson>[0];

  expect(fitJourneyGeoJson(instance, result, true)).toBe(true);
  const [bounds, options] = fitBounds.mock.calls[0];
  expect(bounds.getSouthWest().lng).toBeCloseTo(72.68);
  expect(bounds.getSouthWest().lat).toBeCloseTo(20.5);
  expect(bounds.getNorthEast().lng).toBeCloseTo(72.9);
  expect(bounds.getNorthEast().lat).toBeCloseTo(20.72);
  expect(options).toMatchObject({ padding: 72, maxZoom: 10, duration: 0 });
});
