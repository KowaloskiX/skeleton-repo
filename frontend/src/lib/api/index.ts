/**
 * Public surface of the API client.
 *
 * `./generated/` is produced from `../backend/openapi.json`
 * (`pnpm --filter web generate:api`) and is NOT edited by hand. The rest of the application
 * imports from this file only — enforced by dependency-cruiser
 * (`generated-api-client-is-private`).
 */

export {
  type ApiFailure,
  configureApiClient,
  isStaleCsrfToken,
  isUnattendedFailure,
  isUnauthorized,
} from "./client";
export { apiErrorMessage } from "./errors";
export {
  authLoginMutation,
  authLogoutMutation,
  authRegisterMutation,
  authSessionOptions,
  authSessionQueryKey,
  healthGetOptions,
} from "./generated/@tanstack/react-query.gen";
export type {
  CurrentUserResponse,
  ErrorResponse,
  HealthStatus,
  LoginRequest,
  OrganizationSummary,
  RegisterRequest,
  Role,
  SessionResponse,
} from "./generated/types.gen";
