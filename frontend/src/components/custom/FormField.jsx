import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// Wraps a react-hook-form Controller `field` (value/onChange/onBlur/name/ref) around a
// shadcn Input or Textarea, with a label above and an error message below.
export function FormField({ label, error, multiline = false, className, ...field }) {
  const Control = multiline ? Textarea : Input;

  return (
    <div className={className}>
      <Label htmlFor={field.name} className="mb-1.5 block">
        {label}
      </Label>
      <Control id={field.name} aria-invalid={Boolean(error)} {...field} />
      {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
    </div>
  );
}
