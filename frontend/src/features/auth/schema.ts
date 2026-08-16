import { z } from "zod";

/** Must match `MIN_PASSWORD_LENGTH` on the backend — otherwise the validations drift apart. */
export const MIN_PASSWORD_LENGTH = 12;

export const loginSchema = z.object({
  email: z.email("Enter an email address in the form name@domain.com."),
  password: z.string().min(1, "Enter your password."),
});

export const registerSchema = z.object({
  organizationName: z.string().min(2, "The organization name needs at least 2 characters."),
  email: z.email("Enter an email address in the form name@domain.com."),
  password: z
    .string()
    .min(MIN_PASSWORD_LENGTH, `The password needs at least ${MIN_PASSWORD_LENGTH} characters.`),
});

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
