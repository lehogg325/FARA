import { useState } from "react";
import { CountryView } from "./components/CountryView";
import { DocumentSearchView } from "./components/DocumentSearchView";
import { DocumentView } from "./components/DocumentView";
import { EmptyState } from "./components/EmptyState";
import { Footer } from "./components/Footer";
import { ForeignPrincipalGroupView } from "./components/ForeignPrincipalGroupView";
import { ForeignPrincipalsBrowseView } from "./components/ForeignPrincipalsBrowseView";
import { ForeignPrincipalView } from "./components/ForeignPrincipalView";
import { GuidedTour } from "./components/GuidedTour";
import { RegistrantGroupView } from "./components/RegistrantGroupView";
import { RegistrantView } from "./components/RegistrantView";
import { SearchBox } from "./components/SearchBox";
import { useStore } from "./state/store";

export default function App() {
  const view = useStore((s) => s.view);
  const navigate = useStore((s) => s.navigate);
  const [tourOpen, setTourOpen] = useState(false);

  return (
    <div className="app">
      <header className="app-header">
        <a
          className="masthead"
          href="/"
          title="Back to start"
          onClick={(e) => { e.preventDefault(); navigate({ kind: "home" }); }}
        >
          <span className="kicker">Foreign Agents Registration Act · 1938 – Present</span>
          <h1>The Foreign Agents Registry</h1>
        </a>
        <SearchBox />
        <div className="header-controls">
          {!tourOpen && (
            <button className="header-nav-btn" onClick={() => setTourOpen(true)}>
              Take the tour
            </button>
          )}
          <button
            className="header-nav-btn"
            onClick={() => navigate({ kind: "foreign-principals-browse" })}
          >
            Browse foreign principals
          </button>
        </div>
      </header>

      <main className="main">
        {view.kind === "home" && <EmptyState />}
        {view.kind === "registrant" && <RegistrantView id={view.id} />}
        {view.kind === "registrant-group" && <RegistrantGroupView name={view.name} />}
        {view.kind === "foreign-principal" && <ForeignPrincipalView id={view.id} />}
        {view.kind === "foreign-principal-group" && (
          <ForeignPrincipalGroupView name={view.name} country={view.country} />
        )}
        {view.kind === "foreign-principals-browse" && <ForeignPrincipalsBrowseView />}
        {view.kind === "document" && <DocumentView id={view.id} />}
        {view.kind === "document-search" && <DocumentSearchView q={view.q} />}
        {view.kind === "country" && <CountryView name={view.name} tab={view.tab} />}
      </main>

      <Footer />

      {tourOpen && <GuidedTour onDone={() => setTourOpen(false)} />}
    </div>
  );
}
