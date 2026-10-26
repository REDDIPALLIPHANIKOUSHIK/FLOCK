# PROTOCOL.md — Urja Meter Ops Legacy Portal Protocol Discovery

## 1. Portal Overview
- **Portal URL**: `https://urja-ops.flockenergy.tech`
- **Application Architecture**: Built with **SvelteKit** (SSR with client-side hydration via `@sveltejs/kit`).
- **Authentication Scheme**: Cookie-based server-side session management using `__Secure-better-auth.session_token`.
- **Data Delivery Mechanism**: Hybrid architecture:
  - SvelteKit server routes return server-rendered HTML and `__data.json` endpoints encoded with SvelteKit's *devalue* serialization format.
  - SvelteKit client hooks make background JSON REST requests to `/portal/meters/search`, `/portal/meters/{id}/geo`, `/portal/meters/{id}/energy`, and `/portal/dts`.
  - An HMAC-SHA256 export endpoint `/portal/export` is available using signing secrets retrieved from `/portal/keys`.

---

## 2. Investigation Method
1. **Initial SSR Probing**: Fetched root page HTML, observing SvelteKit script tags referencing immutable entry points and node chunks.
2. **Client Bundle Analysis**: Inspected client JS assets (`entry/app.03ZTmlg3.js`, `nodes/4.2Bgc2kUI.js`, `nodes/5.C4dYcCRt.js`, `nodes/6.l777LXKL.js`, `nodes/7.OkXSQ8CK.js`):
   - Uncovered SvelteKit route dictionary:
     - `/` -> home redirect
     - `/login` -> authentication form (Node 7)
     - `/(portal)/meters` -> meter listing (Node 5)
     - `/(portal)/meters/[id]` -> meter detail & telemetry (Node 6)
     - `/(portal)/transformers` -> distribution transformers (Node 4)
3. **HTTP Probing & Live Traffic Inspection**:
   - Programmatically executed authenticated and unauthenticated HTTP requests to test CSRF behavior, cookie jar persistence, and error structures.

---

## 3. Authentication Flow & CSRF

### Login Handshake
- **Endpoint**: `POST https://urja-ops.flockenergy.tech/login`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Required Headers**:
  - `Origin: https://urja-ops.flockenergy.tech` (Critical: Without this header, SvelteKit's built-in CSRF protection rejects the request with `HTTP 403 Forbidden: Cross-site POST form submissions are forbidden`).
- **Form Fields**:
  - `email`: `operator@urja.local` (Note: the input field is named `email`, not `username`).
  - `password`: `<PORTAL_PASSWORD>`

### Success Response
- **Status**: `HTTP 200 OK` (or `303 See Other`)
- **Headers**:
  ```http
  Set-Cookie: __Secure-better-auth.session_token=<token>; Max-Age=3600; Path=/; HttpOnly; Secure; SameSite=Lax
  ```
- **Body**:
  ```json
  {"type":"redirect","status":303,"location":"/meters"}
  ```

### Failure Response (Invalid Credentials)
- **Status**: `HTTP 200 OK` (Unexpected: Returns 200 rather than 401!)
- **Body**:
  ```json
  {"type":"failure","status":401,"data":"[{\"email\":1,\"error\":2},\"operator@urja.local\",\"Invalid email or password.\"]"}
  ```
- **Adapter Implication**: The adapter checks for the presence of the session cookie and verifies that `type != "failure"`.

### Sign-out
- **Endpoint**: `POST https://urja-ops.flockenergy.tech/api/auth/sign-out`

---

## 4. Discovered Upstream Endpoints

### A. Meter Search / Collection
- **Endpoint**: `GET /portal/meters/search?q={query}&page={page}`
- **Authentication**: Requires session cookie.
- **Unauthenticated Behavior**: Returns `HTTP 401 Unauthorized`:
  ```json
  {"error":"unauthorized","message":"A valid session is required."}
  ```
- **Observed Response Shape**:
  ```json
  {
    "data": [
      {
        "meterId": "J100000",
        "serialNo": "SE33962",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Decommissioned",
        "dtCode": "DT-001"
      },
      {
        "meterId": "J100001",
        "serialNo": "GE84132",
        "make": "L&T",
        "phaseType": "single",
        "installStatus": "Installed",
        "dtCode": "DT-002"
      }
    ],
    "total": 403
  }
  ```
- **Pagination Details**:
  - The upstream portal strictly paginates in fixed-size chunks of 20 items per page (`page=1` maps to items 0..19, `page=2` to 20..39, etc.).
  - Total count observed: 403 meters.
  - Upstream does not support arbitrary `limit` or `offset` query parameters directly on this endpoint.
  - **Adapter Handling**: The API adapter maps arbitrary client `offset` and `limit` to the underlying 20-item pages, fetching multiple pages when requested slices cross page boundaries (e.g. `limit=2, offset=1` or `limit=3, offset=19`) while caching within request memory and respecting `total`.

---

### B. Meter Details (SvelteKit Devalue & SSR HTML)
- **Endpoint**: `GET /meters/{meter_id}/__data.json` with header `x-sveltekit-load: true`
- **Fallback**: `GET /meters/{meter_id}` (SSR HTML page)
- **Data Formats Observed**:
  1. **Legacy Build** (e.g. `J100000`):
     - Detail contains a list of parameter name/value dicts:
       `[{"parameterName": "Meter ID", "parameterValue": "J100000"}, {"parameterName": "Serial No", "parameterValue": "SE33962"}, ...]`
  2. **v2 Build** (e.g. `J100020`):
     - Detail contains a JSON string under `classData`:
       `"{\"installed_meter\":{\"MeterId\":\"J100020\",\"SerialNo\":\"AL20290\",\"Make\":\"Allied\",\"PhaseType\":\"three\",\"InstallationStatus\":\"Installed\",\"InstallationType\":\"CT Operated\"}}"`
  3. **Hierarchy Object**:
     ```json
     {
       "Zone": "Jaipur Zone 1 (Z-01)",
       "Circle": "Circle 1 (C-01)",
       "Division": "Division 1 (D-01)",
       "Subdivision": "Subdivision 1 (SD-01)",
       "Sub Station": "Substation 1 (SS-01)",
       "Feeder": "Feeder 1 (F-001)",
       "DT": "Malviya Nagar DT 1 (DT-001)"
     }
     ```
- **Non-Existent Meter**:
  Returns `HTTP 200` with an error node:
  ```json
  {"type":"error","error":{"message":"Meter not found"},"status":404}
  ```

---

### C. Meter Geographic Coordinates
- **Endpoint**: `GET /portal/meters/{meter_id}/geo`
- **Authentication**: Requires session cookie.
- **Observed Response Shape**:
  ```json
  {
    "data": {
      "latitude": "26.938961002479868",
      "longitude": "75.83095696146852"
    }
  }
  ```

---

### D. Meter Energy / Consumption Telemetry
- **Endpoint**: `GET /portal/meters/{meter_id}/energy?from={YYYY-MM-DD}&to={YYYY-MM-DD}`
- **Authentication**: Requires session cookie.
- **Supported Query Parameters**:
  - `from`: Filters starting date (inclusive).
  - `to`: Filters ending date (inclusive).
- **Observed Response Shape**:
  ```json
  {
    "data": [
      {
        "timestamp": "24/06/2026 00:00",
        "kwh": "48439.16",
        "kvah": "52314.29",
        "voltR": "229"
      },
      {
        "timestamp": "24/06/2026 00:30",
        "kwh": "48439.58",
        "kvah": "52314.75",
        "voltR": "220"
      }
    ]
  }
  ```
- **Interval & Register Characteristics**:
  - Interval: 30 minutes.
  - Active energy (`kwh`): Cumulative register values (increasing monotonically).
  - Apparent energy (`kvah`): Cumulative register values.
  - Voltage (`voltR`): Instantaneous R-phase voltage in Volts.

---

### E. Distribution Transformers & Network Hierarchy
- **Endpoint**: `GET /portal/dts?page={page}`
- **Observed Response Shape**:
  ```json
  {
    "data": [
      {
        "code": "DT-001",
        "name": "Malviya Nagar DT 1",
        "feederCode": "F-001",
        "capacityKva": 100
      },
      {
        "code": "DT-002",
        "name": "Mansarovar DT 2",
        "feederCode": "F-002",
        "capacityKva": 63
      }
    ],
    "total": 40
  }
  ```
- **Hierarchy Mapping**:
  - Distribution Transformers are linked to Feeder codes (`feederCode`).
  - Total number of DTs: 40 across 28 distinct Feeders.
  - Additional hypothetical routes (`/portal/feeders`, `/portal/substations`, `/portal/zones`) return `HTTP 404 Not Found`.

---

### F. HMAC Signed Export Endpoint
- **Key Retrieval**: `GET /portal/keys` -> `{"data":{"signingSecret":"..."}}`
- **Export Endpoint**: `GET /portal/export?page={page}`
- **Headers**:
  - `x-timestamp`: Unix timestamp in seconds.
  - `x-signature`: Hex-encoded HMAC-SHA256 signature of `GET\n/portal/export\npage={page}\n{timestamp}` using the signing secret.
- **Response**: Full JSON export of meters with embedded geo coordinates and hierarchical paths.

---

## 5. Confirmed Findings vs. Unverified Assumptions

| Topic | Status | Evidence / Observation |
|---|---|---|
| Login Route | **Confirmed** | `/login` accepts POST with `email` and `password`. |
| CSRF Header | **Confirmed** | Requires `Origin: https://urja-ops.flockenergy.tech`, otherwise 403 Forbidden. |
| Bad Credentials Status | **Confirmed** | Upstream returns HTTP 200 with `type: failure` payload. |
| Session Expiry Behavior | **Confirmed** | Protected REST calls return HTTP 401; SvelteKit page routes return HTTP 200 with redirect payload. |
| Meters List Endpoint | **Confirmed** | `/portal/meters/search?q=&page=` returns total 403 meters. |
| Dual Detail Formats | **Confirmed** | Legacy meters use parameter arrays; v2 meters use `classData` JSON string. |
| Coordinates Endpoint | **Confirmed** | `/portal/meters/{id}/geo` returns lat/lng strings. |
| Consumption Filtering | **Confirmed** | `from` and `to` query parameters work upstream on `/portal/meters/{id}/energy`. |
| Standalone Feeder Routes | **Confirmed Absent** | `/portal/feeders` returns 404; Feeder topology is inferred from DT `feederCode`. |
| State-changing API Routes | **Omitted / Read-Only** | Assignment strictly required read-only operations; no state-modifying endpoints were tested. |
