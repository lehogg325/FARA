import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type SearchResult } from "../api/client";
import { useStore } from "../state/store";
import { SearchBox } from "./SearchBox";

vi.mock("../api/client", () => ({
  api: { search: vi.fn() },
}));

const REGISTRANT_HIT: SearchResult = {
  entity_type: "registrant",
  entity_id: 42,
  label: "Ballard Partners",
  detail: null,
  registration_number: 1234,
  group_count: 1,
  active_count: 1,
};

const COUNTRY_HIT: SearchResult = {
  entity_type: "country",
  entity_id: null,
  label: "JAPAN",
  detail: null,
  registration_number: null,
  group_count: null,
  active_count: null,
};

beforeEach(() => {
  vi.mocked(api.search).mockReset();
  useStore.setState({ view: { kind: "home" }, history: [] });
});

describe("SearchBox", () => {
  it("fetches and renders results after the debounce delay", async () => {
    vi.mocked(api.search).mockResolvedValue([REGISTRANT_HIT]);
    const user = userEvent.setup();
    render(<SearchBox />);

    await user.type(screen.getByPlaceholderText(/search registrants/i), "ballard");

    await waitFor(() => expect(api.search).toHaveBeenCalledWith("ballard", undefined, expect.anything()));
    expect(await screen.findByText("Ballard Partners")).toBeInTheDocument();
  });

  it("navigates the dropdown with arrow keys and selects with Enter", async () => {
    vi.mocked(api.search).mockResolvedValue([REGISTRANT_HIT, COUNTRY_HIT]);
    const user = userEvent.setup();
    render(<SearchBox />);

    await user.type(screen.getByPlaceholderText(/search registrants/i), "iceland");
    await screen.findByText("Ballard Partners");

    await user.keyboard("{ArrowDown}");
    expect(screen.getByText("Ballard Partners").closest("li")).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowDown}");
    expect(screen.getByText("JAPAN").closest("li")).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Enter}");
    expect(useStore.getState().view).toEqual({ kind: "country", name: "JAPAN" });
  });

  it("closes the dropdown on Escape without navigating", async () => {
    vi.mocked(api.search).mockResolvedValue([REGISTRANT_HIT]);
    const user = userEvent.setup();
    render(<SearchBox />);

    await user.type(screen.getByPlaceholderText(/search registrants/i), "ballard");
    await screen.findByText("Ballard Partners");

    await user.keyboard("{Escape}");
    expect(screen.queryByText("Ballard Partners")).not.toBeInTheDocument();
    expect(useStore.getState().view).toEqual({ kind: "home" });
  });
});
