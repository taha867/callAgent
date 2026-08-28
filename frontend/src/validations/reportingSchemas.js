import { object, date } from "yup";

// yup has no `yupRef` export (that name doesn't exist in the package) — `.test()` against
// `this.parent` is both the real API and the only way to express "until must be STRICTLY
// after since" (ref()-based .min() is an inclusive >= comparison). See
// .claude/plans/phase-3-frontend-implementation-plan.md Correction 1.
export const dateRangeFilterSchema = object({
  since: date().required("Since is required"),
  until: date()
    .required("Until is required")
    .test("is-after-since", "Until must be after since", function (value) {
      const since = this.parent.since;
      return Boolean(value && since && value > since);
    }),
});
