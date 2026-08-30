import { object, string } from "yup";
import { DEFECT_STATUSES, COMPILED_ARTIFACT_TYPES } from "@/utils/constants";

export const defectLogEntryCreateSchema = object({
  title: string().required("Title is required").max(200),
  defectShapeKey: string().required("Shape key is required").max(100),
  demoJourneyId: string().nullable().default(null),
  adversarialScenarioId: string().nullable().default(null),
  language: string().oneOf(["EN", "AR", "CODE_SWITCH"]).default("EN"),
  severity: string().oneOf(["LOW", "MEDIUM", "HIGH"]).default("MEDIUM"),
  notes: string().nullable().max(2000).default(null),
});

export const defectOccurrenceCreateSchema = object({
  shapeKey: string().required("Shape key is required").max(100),
  demoJourneyId: string().nullable().default(null),
  adversarialScenarioId: string().nullable().default(null),
  notes: string().nullable().max(2000).default(null),
});

// Mirrors the backend's DefectLogEntryUpdate, plus the conditional-required rule the
// backend's own compilation_required gate depends on (phase-4-backend-spec.md §0.5) —
// courtesy only, the backend still re-validates (CLAUDE.md §1). Yup has no `.when()`
// precedent anywhere in this codebase — `.test()` + `this.parent` is the real, established
// conditional-validation pattern (see validations/reportingSchemas.js's dateRangeFilterSchema).
export const defectStatusUpdateSchema = object({
  status: string().oneOf(DEFECT_STATUSES).required(),
  compiledArtifactType: string()
    .nullable()
    .test(
      "required-when-compiled",
      "Artifact type is required once status is COMPILED",
      function (value) {
        return this.parent.status !== "COMPILED" || Boolean(value && COMPILED_ARTIFACT_TYPES.includes(value));
      },
    ),
  compiledArtifactRef: string()
    .nullable()
    .max(300)
    .test(
      "required-when-compiled",
      "Artifact reference is required once status is COMPILED",
      function (value) {
        return this.parent.status !== "COMPILED" || Boolean(value);
      },
    ),
  notes: string().nullable().max(2000).default(null),
});
