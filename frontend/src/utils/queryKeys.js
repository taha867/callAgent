export const claimKeys = {
  all: ["claims"],
  detail: (id) => [...claimKeys.all, id],
  status: (id, level) => [...claimKeys.detail(id), "status", level],
  timeline: (id) => [...claimKeys.detail(id), "timeline"],
  documents: (id) => [...claimKeys.detail(id), "documents"],
  garage: (id) => [...claimKeys.detail(id), "garage"],
};

export const callKeys = {
  all: ["calls"],
  detail: (id) => [...callKeys.all, id],
};

export const complaintKeys = {
  all: ["complaints"],
  detail: (id) => [...complaintKeys.all, id],
};
