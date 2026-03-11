# Restructure Notes

- Local professional name: `crypto-market-neutral-platform`
- Base repo: `overseas_exchange_hedge`
- Merged imports:
  - `legacy-imports/hedge-pilot`
  - `legacy-imports/contango-hunter`

## Intent

- Keep `overseas_exchange_hedge` as the production base.
- Absorb reusable Korea hedge logic from `hedge-pilot`.
- Absorb script-based contango workflows from `contango-hunter`.

## Completed Integration

- Renamed the repository to `crypto-market-neutral-platform`.
- Promoted absorbed workflows into first-class CLI entrypoints:
  - `market-neutral-korea-entry`
  - `market-neutral-overseas-entry-manual`
  - `market-neutral-overseas-entry-auto`
  - `market-neutral-korea-exit`
  - `market-neutral-overseas-unwind`
- Kept the original package namespace for compatibility with existing code and tests.

## Remaining Cleanup
1. Decommission archived legacy folders after a separate history-preservation pass.
2. Extract more shared logic if the package namespace is ever renamed.
