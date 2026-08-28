import { useForm, Controller } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import { dateRangeFilterSchema } from "@/validations/reportingSchemas";
import { FormField } from "@/components/custom";
import { Button } from "@/components/ui/button";

// <input type="datetime-local"> needs "YYYY-MM-DDTHH:mm" (local wall-clock, no timezone
// offset) — the browser then parses that string as local time, matching what the user
// actually picked. This is only for populating the input's defaultValue; validation/
// submission works off yup's own Date cast, not this string.
function toDatetimeLocalValue(isoString) {
  const d = new Date(isoString);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function DateRangeFilter({ since, until, onChange }) {
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: yupResolver(dateRangeFilterSchema),
    defaultValues: {
      since: toDatetimeLocalValue(since),
      until: toDatetimeLocalValue(until),
    },
  });

  const onSubmit = (values) => {
    // yup's date() field cast values.since/until into real Date objects during validation.
    // .toISOString() here is the fix for a real bug the naive version would ship: passing
    // the raw Date straight to reportingService.js's query-string builder would silently
    // call Date.prototype.toString() (a browser-locale string), which the backend 422s on.
    // See .claude/plans/phase-3-frontend-implementation-plan.md Correction 2.
    onChange(values.since.toISOString(), values.until.toISOString());
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-wrap items-end gap-4">
      <Controller
        name="since"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            type="datetime-local"
            label="Since"
            error={errors.since?.message}
          />
        )}
      />
      <Controller
        name="until"
        control={control}
        render={({ field }) => (
          <FormField
            {...field}
            type="datetime-local"
            label="Until"
            error={errors.until?.message}
          />
        )}
      />
      <Button type="submit" disabled={isSubmitting}>
        Apply
      </Button>
    </form>
  );
}
