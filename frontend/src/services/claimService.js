import { fetchClient } from "@/middleware/fetchClient";
import { unwrapResponse } from "@/utils/unwrapResponse";

export const getClaim = (claimId) => unwrapResponse(fetchClient(`/claims/${claimId}`));

export const getClaimStatus = (claimId, verificationLevel) =>
  unwrapResponse(fetchClient(`/claims/${claimId}/status?verification_level=${verificationLevel}`));

export const getClaimTimeline = (claimId) =>
  unwrapResponse(fetchClient(`/claims/${claimId}/timeline`));

export const getClaimDocuments = (claimId) =>
  unwrapResponse(fetchClient(`/claims/${claimId}/documents`));

export const getClaimGarage = (claimId) =>
  unwrapResponse(fetchClient(`/claims/${claimId}/garage`));
