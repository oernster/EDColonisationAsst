/**
 * Reading what happened out of a rejected API call.
 *
 * Axios rejects with an error carrying the response; the backend puts its
 * explanation in `detail`. A `catch` binding is `unknown` though, so getting at
 * either means narrowing. Doing that inline at each call site is what left
 * three separate places typing the caught value as `any` instead.
 *
 * Three narrow readers rather than one combined message builder, because the
 * call sites do not agree on what to fall back to and should keep saying so
 * themselves with a plain `||` chain.
 *
 * All three are total: anything at all can be thrown, including null, yet none
 * of these will throw while trying to describe it. Each returns undefined
 * rather than a wrong-typed value, so a FastAPI validation error (whose
 * `detail` is an array, not a string) falls through to the caller's own
 * wording instead of reaching the interface as "[object Object]".
 */

interface ErrorResponseShape {
  status?: unknown
  data?: { detail?: unknown }
}

function propertyOf(value: unknown, name: string): unknown {
  if (typeof value !== 'object' || value === null) {
    return undefined
  }
  return (value as Record<string, unknown>)[name]
}

function responseOf(error: unknown): ErrorResponseShape | undefined {
  const response = propertyOf(error, 'response')
  if (typeof response !== 'object' || response === null) {
    return undefined
  }
  return response as ErrorResponseShape
}

/** The HTTP status of a failed request; undefined if there was no response. */
export function apiErrorStatus(error: unknown): number | undefined {
  const status = responseOf(error)?.status
  return typeof status === 'number' ? status : undefined
}

/** The backend's own explanation, when it sent one as a string. */
export function apiErrorDetail(error: unknown): string | undefined {
  const detail = responseOf(error)?.data?.detail
  return typeof detail === 'string' && detail ? detail : undefined
}

/** The thrown value's own message, which for axios describes the transport. */
export function apiErrorText(error: unknown): string | undefined {
  const message = propertyOf(error, 'message')
  return typeof message === 'string' && message ? message : undefined
}
