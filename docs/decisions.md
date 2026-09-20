# Architectural Decision Records (ADR)

## 2026-09-20 — Choice of SQLite for Database Layer
- **Decided**: Use SQLite as the database engine for Module D backend persistence.
- **Why**: SQLite provides single-file local persistence with zero configuration, zero external service dependency, and effortless reproducibility across demo machines and CI test environments.

## 2026-09-20 — Server-Assigned UUID for Event IDs
- **Decided**: Edge Detection Events (`POST /events`) do not carry an `event_id` in their payload; the backend generates a server-side UUID string upon receipt.
- **Why**: Keeps edge detection scripts stateless and simple, while ensuring globally unique event identifiers for downstream operator feedback and bandit tracking.

## 2026-09-20 — BanditAdapter Abstraction for Module C Decoupling
- **Decided**: Interface Module C via an abstract `BanditAdapter` interface and default `MockBanditAdapter` implementation.
- **Why**: Module C (decision layer) is developed independently. An adapter pattern insulates the FastAPI backend endpoints from internal decision layer changes, allowing a 1-line swap when `RealBanditAdapter` is ready.

## 2026-09-20 — Weight-Only Transmission in Federated Learning
- **Decided**: The Flower FL layer (`cloud/federated/`) transmits policy parameter weight vectors exclusively.
- **Why**: Preserves site data privacy (per project security requirements); raw video frames, detection logs, and operator feedback never cross site boundaries.

## 2026-09-20 — Plain HTML/CSS/JS for Dashboard
- **Decided**: Build the operations console in Vanilla HTML5, CSS3, and JavaScript without frameworks or Node/npm build steps.
- **Why**: Eliminates build-tooling failure risks during live demonstrations while delivering maximum visual customization, crisp typography, and fluid micro-animations through raw CSS.
