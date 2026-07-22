# PSA Telegram Notifier Timeout Fix Implementation Plan

This implementation plan outlines the structural changes to resolve timeout and responsiveness issues in the `psa-telegram-notifier` service.

## Proposed Changes

### notifier.py

#### [MODIFY] [notifier.py](file:///c:/Users/dip.das/.gemini/antigravity-ide/scratch/psa-telegram-notifier/notifier.py)
- Import `socketserver` and `concurrent.futures` at the top of the file.
- Define a `ThreadingHTTPServer` class that inherits from `socketserver.ThreadingMixIn` and `http.server.HTTPServer` with `daemon_threads = True`.
- Update `main()` to instantiate `ThreadingHTTPServer` instead of `http.server.HTTPServer`.
- Refactor `fetch_all_apis()` to use `concurrent.futures.ThreadPoolExecutor` to fetch and parse stats from configured APIs concurrently.
- Refactor `do_POST`'s webhook command handling for `status`/`report` to:
  1. Return `200 OK` immediately back to Telegram.
  2. Launch a daemon thread (`threading.Thread`) to execute `fetch_all_apis()`, format the summary message, and call `send_telegram_notification()`.

---

### test_notifier.py

#### [MODIFY] [test_notifier.py](file:///c:/Users/dip.das/.gemini/antigravity-ide/scratch/psa-telegram-notifier/test_notifier.py)
- Update `test_fetch_all_apis_aggregation()` to handle parallel API polling deterministically by using a request URL-matching mock instead of a simple sequence in `urlopen.side_effect`.

## Verification Plan

### Automated Tests
- Run unit tests to ensure date logic, data parsers, and the parallelized aggregation function work perfectly:
  ```bash
  python -m unittest test_notifier.py
  ```

### Manual Verification
- Run the notifier script locally to verify start-up and server responses:
  ```bash
  python notifier.py
  ```
- Send GET requests to `http://localhost:8080/` (health check) and `http://localhost:8080/pending` (fetch stats) to confirm the multi-threaded server functions correctly.
