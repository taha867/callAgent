import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Wraps a react-hook-form Controller `field` around shadcn's Radix-based Select, adapting
// Radix's onValueChange to RHF's field.onChange. `options` is a flat string[] — every call
// site in this app (CALL_ANSWER_RESULTS, ACTION_CODES) is already a flat array of values
// that also serve as their own display labels.
export function FormSelect({ label, error, options, className, name, value, onChange, onBlur }) {
  return (
    <div className={className}>
      <Label htmlFor={name} className="mb-1.5 block">
        {label}
      </Label>
      <Select value={value} onValueChange={onChange} name={name}>
        <SelectTrigger id={name} className="w-full" aria-invalid={Boolean(error)} onBlur={onBlur}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
    </div>
  );
}
