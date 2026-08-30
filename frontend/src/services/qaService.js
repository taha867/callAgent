import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

function buildQuery(params) {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") usp.set(key, value);
  }
  return usp.toString();
}

export const listDefects = ({ page = 1, pageSize = 20, status, demoJourneyId } = {}) =>
  unwrapResponse(
    fetchClient(
      `/qa/defect-log?${buildQuery({ page, page_size: pageSize, status, demo_journey_id: demoJourneyId })}`,
    ),
  );

export const getDefect = (entryId) => unwrapResponse(fetchClient(`/qa/defect-log/${entryId}`));

export const createDefect = ({
  title,
  defectShapeKey,
  demoJourneyId,
  adversarialScenarioId,
  language,
  severity,
  notes,
}) =>
  unwrapResponse(
    fetchClient("/qa/defect-log", {
      method: "POST",
      body: {
        title,
        defect_shape_key: defectShapeKey,
        demo_journey_id: demoJourneyId ?? null,
        adversarial_scenario_id: adversarialScenarioId ?? null,
        language,
        severity,
        notes: notes ?? null,
      },
    }),
  );

export const recordOccurrence = ({ shapeKey, demoJourneyId, adversarialScenarioId, notes }) =>
  unwrapResponse(
    fetchClient(`/qa/defect-log/${shapeKey}/occurrences`, {
      method: "POST",
      body: {
        demo_journey_id: demoJourneyId ?? null,
        adversarial_scenario_id: adversarialScenarioId ?? null,
        notes: notes ?? null,
      },
    }),
  );

export const updateDefectStatus = ({
  entryId,
  status,
  compiledArtifactType,
  compiledArtifactRef,
  notes,
}) =>
  unwrapResponse(
    fetchClient(`/qa/defect-log/${entryId}`, {
      method: "PATCH",
      body: {
        status,
        compiled_artifact_type: compiledArtifactType ?? null,
        compiled_artifact_ref: compiledArtifactRef ?? null,
        notes: notes ?? null,
      },
    }),
  );

export const listJourneyRuns = (demoJourneyId) =>
  unwrapResponse(
    fetchClient(
      `/qa/journey-runs${demoJourneyId ? `?demo_journey_id=${encodeURIComponent(demoJourneyId)}` : ""}`,
    ),
  );

export const getGovernanceSummary = () => unwrapResponse(fetchClient("/qa/governance-summary"));
