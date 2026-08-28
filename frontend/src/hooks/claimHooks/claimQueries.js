import { useQuery } from "@tanstack/react-query";
import { claimKeys } from "@/utils/queryKeys";
import * as claimService from "@/services/claimService";

export const useClaim = (claimId) =>
  useQuery({
    queryKey: claimKeys.detail(claimId),
    queryFn: () => claimService.getClaim(claimId),
  });

export const useClaimStatus = (claimId, verificationLevel) =>
  useQuery({
    queryKey: claimKeys.status(claimId, verificationLevel),
    queryFn: () => claimService.getClaimStatus(claimId, verificationLevel),
  });

export const useClaimTimeline = (claimId) =>
  useQuery({
    queryKey: claimKeys.timeline(claimId),
    queryFn: () => claimService.getClaimTimeline(claimId),
  });

export const useClaimDocuments = (claimId) =>
  useQuery({
    queryKey: claimKeys.documents(claimId),
    queryFn: () => claimService.getClaimDocuments(claimId),
  });

export const useClaimGarage = (claimId) =>
  useQuery({
    queryKey: claimKeys.garage(claimId),
    queryFn: () => claimService.getClaimGarage(claimId),
  });
