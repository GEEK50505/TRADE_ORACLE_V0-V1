# TRADE_ORACLE Trading Health Report

Generated at UTC: `2026-05-06T09:40:10.864188+00:00`

## Executive Snapshot

- execution backend: `mt5`
- benchmark variant: `super_brain`
- total cycles observed: `38`
- total benchmark events: `152`
- transmit attempts: `36`
- transmit successes: `19`
- broker acceptance rate: `0.527778`
- transmit success rate from attempts: `0.5278`
- pending review runs: `9`
- super brain resumes: `9`
- error events: `0`

## Trading Journey Assessment

This review follows a practical post-trade and trading-operations template built around:

- trade lifecycle coverage: idea -> review -> risk gate -> transmit -> live broker exposure
- execution-quality coverage: transmit attempts, successful transmissions, and observed broker acceptance
- control coverage: pending-review handling, risk rejections, and operational error count
- exposure coverage: what is currently open at the broker

## Cycle Funnel

- cycles observed in report window: `38`
- cycles with pending review: `9`
- cycles with transmit attempt: `35`
- cycles with transmit success: `19`
- cycles with error events: `0`

## Review Conversion

- pending review runs: `9`
- resumed reviews: `9`
- resume to pending ratio: `1.0`

## Forward Journal Outcomes

- `no_trade`: `1`
- `pending_review`: `2`
- `resume_execution_result`: `1`
- `risk_rejected`: `13`

## Current Broker State

- authenticated: `true`
- equity: `10012.17`
- active trades: `2`
- pending orders: `0`
- open positions: `2`
  - `AVAUSD` `BUY` volume `0.01` open `9.47` pnl `2.3`
  - `AVAUSD` `BUY` volume `0.01` open `9.43` pnl `2.7`

## Interpretation

- cycle engine activity: active
- execution quality: some broker-side transmission is proven, but conversion from transmit attempt to successful transmit is still mixed
- risk gate behavior: recent flow is dominated by risk_rejected outcomes, so the system is trading conservatively or hitting broker/risk constraints before live placement

## Missing Metrics

- closed-trade realized PnL history is not yet pulled into this report
- implementation shortfall is not computed because decision-time and fill-time price attribution is not stored as a dedicated metric
- strategy expectancy from live realized closes is not yet available in a canonical report table

## Recent Cycles

| cycle_id | latest_decision | symbols | transmit_succeeded | pending_review | latest_event_at_utc |
| --- | --- | --- | --- | --- | --- |
| `cycle_1778023363040` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-05T23:22:58.507691+00:00` |
| `cycle_1778008937759` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-05T19:22:33.793191+00:00` |
| `cycle_1777994512105` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-05T15:22:11.484011+00:00` |
| `cycle_1777975874586` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-05T10:11:37.85976+00:00` |
| `cycle_1777931047468` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-04T21:44:20.047456+00:00` |
| `cycle_1777916627189` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-04T17:44:00.795279+00:00` |
| `cycle_1777902186192` | `risk_rejected` | `BNB/USDT` | `False` | `False` | `2026-05-04T13:43:34.769578+00:00` |
| `cycle_1777773455704` | `pending_review` | `` | `False` | `True` | `2026-05-03T01:57:52.392186+00:00` |
| `cycle_1777768023195` | `risk_rejected` | `TON/USDT` | `False` | `True` | `2026-05-03T00:27:41.804327+00:00` |
| `cycle_1777753606208` | `risk_rejected` | `ETH/USDT, TON/USDT` | `False` | `True` | `2026-05-02T20:27:25.869334+00:00` |
| `cycle_1777738578861` | `risk_rejected` | `TON/USDT` | `False` | `True` | `2026-05-02T16:38:51.540469+00:00` |
| `cycle_1777736833527` | `resume_execution_result` | `SOL/USDT` | `True` | `True` | `2026-05-02T15:47:25.777586+00:00` |
| `cycle_1777736289025` | `risk_rejected` | `SOL/USDT` | `False` | `True` | `2026-05-02T15:38:19.618896+00:00` |
| `cycle_1777733480164` | `risk_rejected` | `SOL/USDT` | `False` | `True` | `2026-05-02T14:51:48.14293+00:00` |
| `cycle_1777732271557` | `risk_rejected` | `SOL/USDT` | `False` | `True` | `2026-05-02T14:46:03.092594+00:00` |

