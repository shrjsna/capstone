# Operations Dashboard (`dashboard/`)

## 1. Overview & How to Run Locally

The AEGIS Operations Dashboard is a high-performance, dark industrial web console for real-time safety monitoring and human-in-the-loop operator feedback.

### Zero-Build Technology Choice
Built entirely in **Vanilla HTML5, CSS3, and JavaScript** — zero Node/npm dependencies, zero build steps, zero frontend server dependencies.

### Local Run Commands
Serve the `dashboard/` directory using Python's built-in HTTP server:

```bash
# From repository root
python -m http.server 8080 --directory dashboard
```

Open `http://localhost:8080` in any web browser.

---

## 2. API Backend Connections & Configuration

The dashboard connects directly to the FastAPI backend (`cloud/backend/main.py`) via asynchronous `fetch()` API calls:

- **`GET /alerts?limit=50`**: Periodically polled every 2 seconds to render live incoming events.
- **`POST /feedback`**: Emitted when operator clicks **Confirm** or **False Alarm** on an alert card.
- **`GET /thresholds`**: Polled every 2 seconds to update dynamic zone sensitivity meters.
- **`GET /policy-history`**: Fetched on load to display policy version badges and learning history.
- **`POST /events`**: Triggered by synthetic demo buttons (**+ PPE Violation**, **+ Zone Intrusion**).

### Configuring Backend API URL
The top navigation bar contains an **API URL** input field (defaults to `http://127.0.0.1:8000`). If running the backend on a custom port or remote server, update this text field directly in the UI.

---

## 3. Visual Design Intent & Aesthetics

- **Dark Industrial Palette**: Grounded in deep slate charcoal (`#090d14`), avoiding default grey admin templates.
- **Restrained Accent System**: Severity and alert types are distinguished using electric cyan (`#38bdf8`) for Intrusion and warm amber (`#fbbf24`) for PPE violations, preventing color clutter.
- **Tactile Micro-Animations**:
  - New incoming alerts slide into view smoothly (`@keyframes fadeInAlert`).
  - Feedback action buttons feature glowing emerald (`Confirm`) and crimson (`False Alarm`) visual state feedback.
  - Per-zone threshold meters animate smoothly as human operator feedback adjusts sensitivity parameters.

---

## 4. Common Errors & Troubleshooting

1. **Dashboard Shows "No Safety Alerts Detected" & Won't Refresh**
   - *Cause*: FastAPI backend is not running or running on a different port than `http://127.0.0.1:8000`.
   - *Fix*: Ensure `uvicorn cloud.backend.main:app --port 8000` is running. Update the API URL input field in the top header if running on a custom port.

2. **Confirm / False Alarm Clicks Show "Failed to send feedback" Alert**
   - *Cause*: Backend returned 404 because the `event_id` was not found in SQLite, or backend network connection failed.
   - *Fix*: Check browser Developer Tools Console (`F12` -> Network tab) to inspect the `/feedback` HTTP request/response.

3. **CORS Error in Browser Console (`Access to fetch blocked by CORS policy`)**
   - *Cause*: Backend CORS middleware is not active or blocking request origin.
   - *Fix*: The FastAPI backend includes `CORSMiddleware(allow_origins=["*"])`. Verify the backend is running the updated `cloud/backend/main.py`.
