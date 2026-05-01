# TRADE_ORACLE Forward Test Review

Use this after each supervised cycle alongside the n8n `TRADE_ORACLE Forward Test Journal`
Data Table row and the platform benchmark endpoints.

## Run Details

- Date:
- Operator:
- Workflow:
- Cycle ID:
- Run ID:
- Benchmark Variant:
- Execution Backend:

## Outcome

- Final outcome:
- Pending review raised:
- Telegram action taken:
- Thread ID:
- Symbol:
- Direction:
- Order transmitted:

## Benchmark Snapshot

- Benchmark event count:
- Review threads in cycle:
- Risk recheck outcome:
- Execution outcome:

## Operator Notes

- What looked strong:
- What looked weak:
- Any market regime mismatch:
- Any execution friction:
- Any broker or MT5 anomaly:

## Follow-Up

- Adjust watchlist:
- Adjust risk or symbol mapping:
- Investigate thread/audit details:
- Keep strategy unchanged for next cycle:

## Suggested Checks

```powershell
curl http://127.0.0.1:8000/system/benchmark/cycles/recent
curl http://127.0.0.1:8000/system/benchmark/cycle/<cycle-id>
curl http://127.0.0.1:8000/system/benchmark/summary
curl http://127.0.0.1:8000/system/audit/thread/<thread-id>
```
