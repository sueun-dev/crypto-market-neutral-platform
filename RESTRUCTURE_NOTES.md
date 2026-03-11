# Restructure Notes

- Local professional name: `crypto-market-neutral-platform`
- Base repo: `overseas_exchange_hedge`

## Intent

- Keep `overseas_exchange_hedge` as the production base.
- Absorb reusable Korea hedge logic from the previous standalone hedge entry repository.
- Absorb script-based contango workflows from the previous standalone auto-entry repository.

## Completed Integration

- Renamed the repository to `crypto-market-neutral-platform`.
- Promoted absorbed workflows into first-class CLI entrypoints:
  - `market-neutral-korea-entry`
  - `market-neutral-overseas-entry-manual`
  - `market-neutral-overseas-entry-auto`
  - `market-neutral-korea-exit`
  - `market-neutral-overseas-unwind`
- Removed archived source copies after the merged workflows were validated.
- Kept the original package namespace for compatibility with existing code and tests.

## Remaining Cleanup
1. Extract more shared logic if the package namespace is ever renamed.
