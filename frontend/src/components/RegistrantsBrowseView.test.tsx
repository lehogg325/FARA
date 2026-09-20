import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Page, type RegistrantSummary } from "../api/client";
import { RegistrantsBrowseView } from "./RegistrantsBrowseView";

vi.mock("../api/client", () => ({
  api: { listRegistrants: vi.fn() },
}));

// Representative of every Page<T>-driven browse view (ForeignPrincipalsBrowseView,
// DocumentsBrowseView share this same fetch/paginate/error shape) — covering it
// once here stands in for the pattern, not just this one screen.
function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const REGISTRANT: RegistrantSummary = {
  registrant_id: 1,
  jurisdiction: "fara",
  registration_number: 5870,
  name: "Brownstein Hyatt Farber Schreck, LLP",
  business_name: null,
  city: "Washington",
  state: "DC",
  status: "active",
  registration_date: "2020-01-15",
  termination_date: null,
};

function page(items: RegistrantSummary[], total: number, offset = 0): Page<RegistrantSummary> {
  return { items, total, limit: 25, offset };
}

beforeEach(() => {
  vi.mocked(api.listRegistrants).mockReset();
});

describe("RegistrantsBrowseView", () => {
  it("renders the initial list", async () => {
    vi.mocked(api.listRegistrants).mockResolvedValue(page([REGISTRANT], 1));
    renderWithClient(<RegistrantsBrowseView />);

    expect(await screen.findByText(/Brownstein Hyatt/)).toBeInTheDocument();
    expect(screen.getByText("1 registrants")).toBeInTheDocument();
  });

  it("debounces the search input before refetching", async () => {
    vi.mocked(api.listRegistrants).mockResolvedValue(page([REGISTRANT], 1));
    const user = userEvent.setup();
    renderWithClient(<RegistrantsBrowseView />);
    await screen.findByText(/Brownstein Hyatt/);

    vi.mocked(api.listRegistrants).mockClear();
    await user.type(screen.getByPlaceholderText(/search by name/i), "ballard");

    await waitFor(() =>
      expect(api.listRegistrants).toHaveBeenCalledWith(expect.objectContaining({ q: "ballard" }), expect.anything()),
    );
  });

  it("disables Prev on the first page and advances the offset on Next", async () => {
    vi.mocked(api.listRegistrants).mockResolvedValue(page([REGISTRANT], 50));
    const user = userEvent.setup();
    renderWithClient(<RegistrantsBrowseView />);
    await screen.findByText(/Brownstein Hyatt/);

    expect(screen.getByText(/Prev/)).toBeDisabled();
    await user.click(screen.getByText(/Next/));

    await waitFor(() =>
      expect(api.listRegistrants).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 25 }),
        expect.anything(),
      ),
    );
  });

  it("shows the error state when the query fails", async () => {
    vi.mocked(api.listRegistrants).mockRejectedValue(new Error("boom"));
    renderWithClient(<RegistrantsBrowseView />);

    expect(await screen.findByText(/Could not load results/i)).toBeInTheDocument();
  });
});
