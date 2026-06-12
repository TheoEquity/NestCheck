# V1.0 Test Plan

This document records the focused verification scope for the V1.0 stable-nest fund UI and API surface.

## Scope

- Stable-nest fund overview page at `/assets/diagnosis`.
- Internal fund NAV and share history used by asset management and diagnosis pages.
- Market index history API used to build benchmark curves.
- System settings category navigation after hiding the backtest category from the Web UI.

## Required Checks

Backend:

- `python3 -m unittest tests.test_market_api`
- `python3 -m unittest tests.test_portfolio_api.PortfolioApiTestCase.test_fund_reset_updates_today_record tests.test_portfolio_api.PortfolioApiTestCase.test_fund_history_returns_one_latest_record_per_day`

Frontend:

- `npm run test -- src/App.test.tsx src/pages/__tests__/SettingsPage.test.tsx`
- `npx eslint src/App.test.tsx src/pages/SettingsPage.tsx src/pages/__tests__/SettingsPage.test.tsx`
- `npm run build`

## Test Inventory Notes

- The legacy Web backtest page, its frontend API wrapper, and its page test were removed because `/backtest` now redirects to `/assets/diagnosis` and no active navigation exposes the legacy backtest workflow.
- Backend backtest tests remain valid because the FastAPI backtest router, CLI/service paths, and read-only agent tooling still exist.
- Alert documentation tests remain valid because alert docs and runtime contracts still exist.

## Known Gaps

- Full `tests.test_portfolio_api` currently includes snapshot replay failures unrelated to V1.0 fund history: replay snapshot positions omit fields required by `PortfolioSnapshotResponse` validation.
- Full frontend lint has pre-existing unrelated issues outside the V1.0 files; use targeted lint for this change set until those are addressed.
