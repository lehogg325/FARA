import { useEffect, useState } from "react";
import { useStore, type View } from "../state/store";

interface TourStep {
  title: string;
  subtitle: string;
  body: string;
  view: View;
}

const TOUR_STEPS: TourStep[] = [
  {
    title: "What Is FARA?",
    subtitle: "Step 1 of 6",
    body: "The Foreign Agents Registration Act requires anyone in the U.S. who's paid to represent a foreign government, company, or political party — lobbying, PR, political consulting — to publicly disclose it to the Department of Justice. This tour walks through one real country's filings, start to finish.",
    view: { kind: "home" },
  },
  {
    title: "Pick A Country",
    subtitle: "Step 2 of 6",
    body: "China is one of four countries pinned at the top of Browse by country as a foreign adversary. These numbers — active registrants, foreign principals, reportable contacts, political contributions — are counted live from real DOJ filings, not estimates.",
    view: { kind: "country", name: "CHINA", tab: "overview" },
  },
  {
    title: "The Network",
    subtitle: "Step 3 of 6",
    body: "Every orange node is a foreign principal — a foreign government, company, or party. Every blue node is the U.S. registrant representing them. Hover any node to see its name; click a registrant to expand who they've actually contacted and who received their political contributions.",
    view: { kind: "country", name: "CHINA", tab: "network" },
  },
  {
    title: "What They're Doing",
    subtitle: "Step 4 of 6",
    body: "Every filing describes the registrant's actual reported activity. FARA classifies that language into topics automatically — media relations, diplomacy, trade, lobbying, and more — so you can see at a glance what China's registered agents report doing.",
    view: { kind: "country", name: "CHINA", tab: "topics" },
  },
  {
    title: "One Registrant, In Full",
    subtitle: "Step 5 of 6",
    body: "Zoom from a whole country down to a single filer. Ballard Partners is a real, active registrant — this page shows every foreign principal they represent, every document they've filed with the DOJ, and the political activity disclosed in it.",
    view: { kind: "registrant", id: 540 },
  },
  {
    title: "Search The Filings Themselves",
    subtitle: "Step 6 of 6",
    body: "Beyond structured data, every filing's full text is searchable — OCR'd from scanned decades-old forms and parsed natively from recent ones. Search the actual language registrants used to describe their work, not just names and dates.",
    view: { kind: "document-search", q: "lobbying strategy" },
  },
];

const SUGGESTIONS = [
  {
    label: "Compare adversaries",
    body: "Browse Russia, Iran, or North Korea next to China — same tabs, same structure, very different numbers.",
  },
  {
    label: "Search a name you recognize",
    body: "Type any lobbying firm, PR agency, or public figure into the search box up top and see what's on file.",
  },
  {
    label: "Read a full filing",
    body: "Open any document from a registrant's profile — full text, extracted fields, and the original filing side by side.",
  },
];

function Dots({ total, current }: { total: number; current: number }) {
  return (
    <div className="tour-dots">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className={`tour-dot${i === current ? " active" : ""}`} />
      ))}
    </div>
  );
}

function StepCard({
  step,
  stepIndex,
  total,
  onNext,
  onBack,
  onSkip,
}: {
  step: TourStep;
  stepIndex: number;
  total: number;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const isLast = stepIndex === total - 1;
  return (
    <div className="tour-card">
      <Dots total={total} current={stepIndex} />
      <div className="tour-eyebrow">{step.subtitle}</div>
      <div className="tour-title">{step.title}</div>
      <p className="tour-body">{step.body}</p>
      <div className="tour-actions">
        <button className="tour-btn" onClick={onSkip}>Skip</button>
        <div style={{ display: "flex", gap: 8 }}>
          {stepIndex > 0 && <button className="tour-btn" onClick={onBack}>&larr; Back</button>}
          <button className="tour-btn tour-btn-primary" onClick={onNext}>{isLast ? "Finish →" : "Next →"}</button>
        </div>
      </div>
    </div>
  );
}

function SuggestionCard({ onDone }: { onDone: () => void }) {
  return (
    <div className="tour-card tour-card-wide">
      <div className="tour-eyebrow">Tour complete — try this next</div>
      <div className="tour-title">Three things worth exploring</div>
      <div className="tour-suggestions">
        {SUGGESTIONS.map((s) => (
          <div className="tour-suggestion" key={s.label}>
            <div className="tour-suggestion-label">{s.label}</div>
            <div className="tour-suggestion-body">{s.body}</div>
          </div>
        ))}
      </div>
      <div className="tour-actions" style={{ justifyContent: "flex-end" }}>
        <button className="tour-btn tour-btn-primary" onClick={onDone}>Start exploring &rarr;</button>
      </div>
    </div>
  );
}

export function GuidedTour({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const navigate = useStore((s) => s.navigate);

  useEffect(() => {
    navigate(TOUR_STEPS[0].view);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function goTo(i: number) {
    setStep(i);
    navigate(TOUR_STEPS[i].view);
  }

  function next() {
    if (step < TOUR_STEPS.length - 1) goTo(step + 1);
    else setShowSuggestions(true);
  }

  function back() {
    if (step > 0) goTo(step - 1);
  }

  if (showSuggestions) {
    return <SuggestionCard onDone={onDone} />;
  }

  return (
    <StepCard
      step={TOUR_STEPS[step]}
      stepIndex={step}
      total={TOUR_STEPS.length}
      onNext={next}
      onBack={back}
      onSkip={onDone}
    />
  );
}
