# P37 — next version (outside the V1 scope frozen at the Design gate)

| Item | Why not in V1 | Source |
|---|---|---|
| Real-Time Dashboard over the Eventhouse | nice-to-have in the brief | brief §5 row 16 |
| Activator alert (email or Teams) | owner: not now; not established on this tenant | brief §5 row 17, owner 2026-11-23 |
| Live replay through an Eventstream custom endpoint | owner chose KQL hourly batches | owner 2026-11-23 |
| Quantile models for the forecast range | V1 uses backtest residual quantiles | Design Package, forecast tab |
| Weather from a real source | V1 temperature is generated | Design Package, data tab |
| Workspace-side Git sync | needs a GitHub connection for the new repo (a token) | probe PR6, brief Rev 2 |
| Drift detector (slow change over weeks) | the V1 detector looks for sharp changes | Design Package, detector |
