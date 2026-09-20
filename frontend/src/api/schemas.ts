// Runtime validation for the highest-traffic endpoints (search, meta, country
// detail) — everything else in client.ts still trusts a bare `as` cast. These
// schemas mirror the matching TS interfaces in client.ts field-for-field; if
// they drift, that's a bug to fix in whichever one is wrong, not a reason to
// loosen the schema.
import { z } from "zod";

export const entityTypeSchema = z.enum(["registrant", "foreign_principal", "short_form_registrant", "country"]);

export const searchResultSchema = z.object({
  entity_type: entityTypeSchema,
  entity_id: z.number().nullable(),
  label: z.string(),
  detail: z.string().nullable(),
  registration_number: z.number().nullable(),
  group_count: z.number().nullable(),
  active_count: z.number().nullable(),
});
export const searchResultsSchema = z.array(searchResultSchema);

const datasetStatusSchema = z.object({
  dataset: z.string(),
  snapshot_date: z.string(),
  loaded_row_count: z.number(),
  status: z.string(),
  finished_at: z.string().nullable(),
});

const extractionCoverageSchema = z.object({
  stage: z.string(),
  succeeded_count: z.number(),
  eligible_count: z.number(),
});

export const metaSchema = z.object({
  jurisdiction: z.string(),
  data_as_of: z.string().nullable(),
  datasets: z.array(datasetStatusSchema),
  extraction_coverage: z.array(extractionCoverageSchema),
});

export const countryDetailSchema = z.object({
  country_name: z.string(),
  active_registrant_count: z.number(),
  total_registrant_count: z.number(),
  foreign_principal_count: z.number(),
  contact_count: z.number(),
  contribution_total: z.number().nullable(),
  contribution_count: z.number(),
});
