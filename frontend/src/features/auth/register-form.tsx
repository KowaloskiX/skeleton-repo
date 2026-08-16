import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { ErrorCallout } from "@/components/ui/callout";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiErrorMessage } from "@/lib/api";

import { useRegister } from "./mutations";
import { MIN_PASSWORD_LENGTH, type RegisterValues, registerSchema } from "./schema";

export function RegisterForm(): ReactNode {
  const { register: submitRegistration, isPending, error } = useRegister();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { organizationName: "", email: "", password: "" },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={handleSubmit((values) => submitRegistration(values))}
      noValidate
    >
      {error && <ErrorCallout>{apiErrorMessage(error)}</ErrorCallout>}

      <Field
        htmlFor="organizationName"
        label="Organization"
        hint="You will become its owner."
        error={errors.organizationName?.message}
      >
        <Input
          id="organizationName"
          autoComplete="organization"
          aria-invalid={errors.organizationName ? true : undefined}
          aria-describedby="organizationName-message"
          {...register("organizationName")}
        />
      </Field>

      <Field htmlFor="email" label="Email" error={errors.email?.message}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby="email-message"
          {...register("email")}
        />
      </Field>

      <Field
        htmlFor="password"
        label="Password"
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        error={errors.password?.message}
      >
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby="password-message"
          {...register("password")}
        />
      </Field>

      <Button type="submit" className="w-full" disabled={isPending}>
        {isPending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
