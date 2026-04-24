# My Awesome Library

A library for doing awesome things.

## [Unreleased]

### Added
- Dark mode support
- New `export_csv()` function

## [2.1.0] - 2024-11-15

### Added
- WebSocket support for real-time updates
- New `batch_process()` method for handling multiple items at once
- Configurable retry logic with exponential backoff

### Fixed
- Memory leak in connection pool when connections timeout
- Incorrect timezone handling in `parse_datetime()` for UTC offsets

### Changed
- Improved error messages to include context and suggested fixes

## [2.0.0] - 2024-09-01

### Breaking
- Renamed `connect()` to `open_connection()` — update all call sites
- Removed deprecated `legacy_auth` parameter from `authenticate()`

### Added
- Full async/await support across all public API methods
- Plugin architecture for custom data processors
- Type stubs (.pyi files) for better IDE support

### Removed
- Dropped support for Python 3.8 and 3.9
- Removed `SyncClient` class — use `AsyncClient` with `asyncio.run()`

### Security
- Patched SSRF vulnerability in URL validation logic (CVE-2024-1234)

## [1.4.2] - 2024-06-10

### Fixed
- Crash when input file contains null bytes
- Race condition in multi-threaded download manager
- Off-by-one error in pagination cursor calculation

### Security
- Updated dependencies to address CVE-2024-5678 in requests library

## [1.4.0] - 2024-04-22

### Added
- Support for gzip-compressed responses
- `Changelog.from_url()` class method for remote changelogs

### Changed
- Default timeout increased from 10s to 30s
- Logging now uses structured JSON format

### Deprecated
- `SyncClient` is deprecated and will be removed in v2.0.0
