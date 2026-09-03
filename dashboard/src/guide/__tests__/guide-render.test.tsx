import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CONCEPTS } from "../concepts";
import { GuidePage } from "../GuidePage";
import { SCREENS } from "../registry";

function renderGuide(initialEntry = "/guide") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <GuidePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("guide reference page", () => {
  it("renders a section for every screen in the model", () => {
    renderGuide();
    for (const s of SCREENS) {
      expect(screen.getByRole("heading", { name: s.title, level: 2 })).toBeInTheDocument();
    }
  });

  it("renders every concept", () => {
    const { container } = renderGuide();
    // Scoped to the concepts list, because a term such as "Peer group" also appears in the
    // prose of the controls that surface it.
    const terms = Array.from(container.querySelectorAll("#guide-concepts dt")).map((el) => el.textContent);
    expect(terms).toEqual(CONCEPTS.map((c) => c.term));
  });

  it("narrows to one screen when the screen filter is set", () => {
    renderGuide("/guide?screen=portfolio");
    expect(screen.getByRole("heading", { name: "Portfolio overview", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Audit log", level: 2 })).not.toBeInTheDocument();
  });

  it("narrows to matching controls when searching", () => {
    renderGuide("/guide?q=threshold");
    expect(screen.getByRole("heading", { name: "Cost of a false negative", level: 3 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Collapse navigation", level: 3 })).not.toBeInTheDocument();
  });

  it("says so rather than rendering nothing when a search matches no control", () => {
    renderGuide("/guide?q=zzzznotathing");
    expect(screen.getByText(/Nothing matches those words/)).toBeInTheDocument();
  });
});
