import { describe, expect, it } from "vitest";

import { isStaleCsrfToken, isUnattendedFailure, isUnauthorized } from "./client";

describe("isUnauthorized", () => {
  it("recognizes 401 as an expired session", () => {
    expect(isUnauthorized({ code: "session_invalid", message: "…", status: 401 })).toBe(true);
  });

  it("does not confuse 401 with other API errors", () => {
    // 403 is an invalid CSRF token, 422 is validation — neither means "sign the user out",
    // and such a redirect would lose a filled-in form.
    expect(isUnauthorized({ code: "csrf_invalid", status: 403 })).toBe(false);
    expect(isUnauthorized({ status: 422 })).toBe(false);
  });

  it("tolerates errors with no status (the request never reached the server)", () => {
    expect(isUnauthorized({ message: "Failed to fetch" })).toBe(false);
    expect(isUnauthorized(new Error("offline"))).toBe(false);
    expect(isUnauthorized(null)).toBe(false);
    expect(isUnauthorized(undefined)).toBe(false);
  });
});

describe("isStaleCsrfToken", () => {
  it("recognizes a stale token by the error code, not by the status alone", () => {
    expect(isStaleCsrfToken({ code: "csrf_invalid", status: 403 })).toBe(true);
  });

  it("ignores other 403s", () => {
    // A 403 with a different code is an authorization decision ("you lack permission"), not a
    // token problem — refreshing the session would change nothing.
    expect(isStaleCsrfToken({ code: "forbidden", status: 403 })).toBe(false);
    expect(isStaleCsrfToken({ code: "csrf_invalid", status: 401 })).toBe(false);
  });
});

describe("isUnattendedFailure", () => {
  it("covers what nothing else will show: server failures and requests that never left", () => {
    expect(isUnattendedFailure({ status: 500 })).toBe(true);
    expect(isUnattendedFailure({ status: 503 })).toBe(true);
    // No status means the request never reached the server — offline, DNS, a dead backend.
    expect(isUnattendedFailure(new Error("Failed to fetch"))).toBe(true);
  });

  it("stays quiet for failures a component is already showing", () => {
    // Toasting these would double up on the message the form renders next to the field.
    expect(isUnattendedFailure({ status: 401 })).toBe(false);
    expect(isUnattendedFailure({ status: 403 })).toBe(false);
    expect(isUnattendedFailure({ status: 409 })).toBe(false);
    expect(isUnattendedFailure({ status: 422 })).toBe(false);
  });
});
