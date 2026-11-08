# Integration verification — November 8, 2026

Changes are prepared on `integrations-setup`, based on `branch_eman_v2`.
Credentials belong in the Git-ignored root `.env`; they are not included here.

| Integration | Evidence | Remaining work |
| --- | --- | --- |
| Gemini | Live advisor response returned `clement-gemini`; Explain cards checked in the UI. | Avatar generation was not tested. |
| Solana | User signed a Devnet savings-goal memo; UI showed on-chain verification and Explorer link. | Public RPC airdrop returned HTTP 410; use the external Devnet faucet. |
| Snowflake | Student account returned a non-empty Insights review using `mistral-large3`; user verified it in the UI. | Replace the one-hour token network-policy bypass with a user-scoped policy allowing the deployment's egress IP. |
| Tiger Data | TimescaleDB 2.31.0; 1,056,320 transactions; 4,500 accounts; four hypertables and daily/monthly continuous aggregates. All accounts' I/S/F/H/B/P matched the original SQLite database. App health reports PostgreSQL and account summaries load. | Deployment configuration and ongoing resource monitoring. |
| Vultr | Not deployed. | Sponsor credits or user-approved paid hosting. |

## Snowflake changes

The adapter now calls parameterized `AI_COMPLETE` through the SQL API, polls unfinished statements, and decodes SQL result cells. This avoids legacy functions/models blocked on the new student account and the direct inference endpoint's model rejection. The configured token role also needs warehouse USAGE. See `SETUP_INTEGRATIONS.md`.

## Measured Tiger Data benchmark

See [the recorded measurements](benchmarks/tiger_data_benchmark.json). These are five-run client-side query timings on the shared service, including fetching results, not general performance guarantees:

| Query | Raw median | Aggregate median | Ratio (raw / aggregate) |
| --- | ---: | ---: | ---: |
| All-account monthly cash flow | 3339.62 ms | 1811.47 ms | 1.84 |
| One-account daily cash flow | 27.48 ms | 25.94 ms | 1.06 |
| Total 2025 flow | 97.78 ms | 188.13 ms | 0.52 |

The total-flow aggregate was slower. Do not claim every query improved.

Only the supplied challenge datasets and derived baselines were imported into Tiger Data. Local user preferences, saved goals, and other app records remain in the original SQLite database; those were not migrated. A previously recorded Devnet transaction remains public on-chain.
