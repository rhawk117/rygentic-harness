# Project

An internal service.

## Commands

- Test: `npm test`
- Build: `npm run build`

## Engineering rules

- Never log secrets or raw tokens in any environment, including local development.
- Every new endpoint must include input validation, authorization checks, and unit tests.
- Prefer small composable functions over large multi-purpose handlers.

## Python Style Guide

- Indentation: 2 spaces
- Line Length: Maximum 80 characters
- function_and_variable_names: snake_case
- ClassNames: PascalCase
- Imports: organized and sorted

## Plugin System

See `docs/plugin-reorg.md` for details.

## Adding a new OS to quickget

1. Entry in `os_info()` case statement
2. `releases_<os>()` function returning available versions
3. `arch_<os>()` function if ARM64 is supported
