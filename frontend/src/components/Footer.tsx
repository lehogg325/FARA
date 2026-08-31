import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function Footer() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
  if (!meta.data) return null;
  const llm = meta.data.extraction_coverage.find((c) => c.stage === "fields_llm");
  return (
    <footer className="app-footer">
      <p>
        Data mined from the FARA eFile system (efile.fara.gov), last refreshed {meta.data.data_as_of ?? "unknown"}.
        {llm && ` ${llm.succeeded_count} of ${llm.eligible_count} eligible filings have LLM-assisted narrative extraction.`}
        {" "}Narrative fields are machine-extracted and may contain errors — always verify against the source PDF.
      </p>
    </footer>
  );
}
