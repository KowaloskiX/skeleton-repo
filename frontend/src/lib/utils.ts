import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merges Tailwind classes so the later one wins a conflict (the shadcn/ui pattern). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
