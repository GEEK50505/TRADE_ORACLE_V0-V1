# TRADE_ORACLE Trading Health Report

Generated at UTC: `2026-06-02T05:35:51.649719+00:00`

## Executive Snapshot

- execution backend: `mt5`
- benchmark variant: `super_brain`
- total cycles observed: `70`
- total benchmark events: `284`
- transmit attempts: `48`
- transmit successes: `28`
- broker acceptance rate: `0.583333`
- transmit success rate from attempts: `0.5833`
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

- cycles observed in report window: `50`
- cycles with pending review: `8`
- cycles with transmit attempt: `28`
- cycles with transmit success: `12`
- cycles with error events: `0`

## Review Conversion

- pending review runs: `9`
- resumed reviews: `9`
- resume to pending ratio: `1.0`

## Forward Journal Outcomes

- `execution_result`: `9`
- `no_trade`: `21`
- `pending_review`: `2`
- `resume_execution_result`: `1`
- `risk_rejected`: `16`

## Current Broker State

- authenticated: `true`
- equity: `50002.19`
- active trades: `3`
- pending orders: `1`
- open positions: `3`
  - `DOGEUSD` `SELL` volume `0.01` open `0.1006` pnl `0.76`
  - `DOGEUSD` `SELL` volume `0.01` open `0.1006` pnl `0.76`
  - `DOGEUSD` `SELL` volume `0.01` open `0.1006` pnl `0.76`

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
| `cycle_1780378466969` | `no_trade` | `` | `False` | `False` | `2026-06-02T05:34:45.55802+00:00` |
| `cycle_1780374828970` | `execution_result` | `DOGE/USDT` | `True` | `False` | `2026-06-02T04:34:05.075629+00:00` |
| `cycle_1780374380655` | `execution_result` | `DOGE/USDT` | `True` | `False` | `2026-06-02T04:26:38.087087+00:00` |
| `cycle_1780374297752` | `execution_result` | `DOGE/USDT` | `True` | `False` | `2026-06-02T04:25:13.623092+00:00` |
| `cycle_1780373928715` | `execution_result` | `DOGE/USDT` | `True` | `False` | `2026-06-02T04:19:06.132191+00:00` |
| `cycle_1780372665161` | `risk_rejected` | `DOGE/USDT` | `False` | `False` | `2026-06-02T03:58:01.823201+00:00` |
| `cycle_1779137267972` | `no_trade` | `` | `False` | `False` | `2026-05-18T20:47:57.875248+00:00` |
| `cycle_1779133633773` | `no_trade` | `` | `False` | `False` | `2026-05-18T19:47:27.680118+00:00` |
| `cycle_1779119190107` | `no_trade` | `` | `False` | `False` | `2026-05-18T15:46:40.790401+00:00` |
| `cycle_1778987904603` | `no_trade` | `` | `False` | `False` | `2026-05-17T03:18:42.995132+00:00` |
| `cycle_1778857423711` | `risk_rejected` | `XRP/USDT` | `False` | `False` | `2026-05-15T15:03:58.654913+00:00` |
| `cycle_1778748059600` | `risk_rejected` | `XRP/USDT` | `False` | `False` | `2026-05-14T08:42:10.500335+00:00` |
| `cycle_1778646579567` | `no_trade` | `` | `False` | `False` | `2026-05-13T04:29:57.053966+00:00` |
| `cycle_1778594792052` | `execution_result` | `XRP/USDT` | `True` | `False` | `2026-05-12T14:06:53.46062+00:00` |
| `cycle_1778526386886` | `no_trade` | `` | `False` | `False` | `2026-05-11T19:06:46.35474+00:00` |

