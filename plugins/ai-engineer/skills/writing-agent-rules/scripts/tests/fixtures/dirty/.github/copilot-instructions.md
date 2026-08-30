# Project

An internal service that exposes a small HTTP API to internal consumers.

## Commands

- Test: `npm test`
- Build: `npm run build`

## Engineering rules

- Never log secrets or raw tokens in any environment, including local development.
- Every new endpoint must include input validation, authorization checks, and unit tests.
- Prefer small composable functions over large multi-purpose handlers.
