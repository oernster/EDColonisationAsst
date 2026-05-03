# GameGlass Integration

This document describes how a GameGlass shard (or any embedded web view) should talk to the ED Colonisation Assistant backend. It focuses on:

- The HTTP **API endpoints** exposed by the assistant
- The **request / response shapes** that are relevant to GameGlass
- How to obtain a **shopping list of commodities** for construction sites


## 1. Backend Overview

The backend is a FastAPI service that exposes:

- **REST endpoints** under the `/api` prefix
- **AJAX long-poll endpoint** at `/api/changes/longpoll` for live updates

By default the service listens on `http://localhost:<port>`, where the port is configured in the backend configuration (see the main application README / config). When developing a GameGlass shard on the same machine, the typical base URLs are:

- `http://localhost:<port>/api/...` for HTTP requests
- `http://localhost:<port>/api/changes/longpoll` for long-poll live updates

CORS is configured to allow browser-based clients, so calls from the shard’s embedded web view are permitted as long as they target the correct origin and port.


## 2. Key REST Endpoints for GameGlass

This section documents the endpoints that a GameGlass shard is expected to use, especially for displaying:

- Construction sites (per-system and across all systems)
- A **shopping list of required commodities**


### 2.1. List All Construction Sites

**Method:** GET  
**Path:** `/api/sites`

**Purpose**

Returns **all construction sites** known to the assistant, split into **in-progress** and **completed** categories. This is a convenient way to populate a main site list in a shard.

**Successful Response (shape)**

```json
{
  "in_progress_sites": [
    {
      "market_id": 123456,
      "station_name": "Example Depot",
      "station_type": "Outpost",
      "system_name": "LHS 1234",
      "system_address": 1234567890,
      "construction_progress": 42.5,
      "construction_complete": false,
      "construction_failed": false,
      "commodities": [
        {
          "name": "water",
          "name_localised": "Water",
          "required_amount": 1000,
          "provided_amount": 250,
          "remaining_amount": 750,
          "progress_percentage": 25.0,
          "payment": 250000,
          "status": "in_progress"
        }
      ],
      "total_commodities_needed": 750,
      "commodities_progress_percentage": 25.0,
      "last_updated": "2025-01-01T12:00:00Z",
      "last_source": "journal"
    }
  ],
  "completed_sites": [
    {
      "market_id": 987654,
      "station_name": "Finished Depot",
      "station_type": "Coriolis",
      "system_name": "LHS 5678",
      "system_address": 987654321,
      "construction_progress": 100.0,
      "construction_complete": true,
      "construction_failed": false,
      "commodities": [],
      "total_commodities_needed": 0,
      "commodities_progress_percentage": 100.0,
      "last_updated": "2025-01-02T10:00:00Z",
      "last_source": "journal"
    }
  ]
}
```

Notes:

- The `commodities` array on each site contains **per-commodity progress**.
- The fields `total_commodities_needed` and `commodities_progress_percentage` summarize the commodity situation for each site.
- You can use this endpoint to:
  - Render global lists of depots
  - Build a **global shopping list** by aggregating `commodities` across **all** sites in the shard itself


### 2.2. Systems and System Selection

These endpoints help present and filter data by star system.


#### 2.2.1. List Systems with Construction Sites

**Method:** GET  
**Path:** `/api/systems`

**Purpose**

Returns a list of system names that currently have construction sites.

**Response Example**

```json
{
  "systems": [
    "LHS 1234",
    "LHS 5678"
  ]
}
```

Typical usage: populate a system dropdown or allow manual system selection in the shard.


#### 2.2.2. Search Systems (Autocomplete)

**Method:** GET  
**Path:** `/api/systems/search`  
**Query Parameters:**

- `q` (required, string): case-insensitive search term

**Response Example**

```json
{
  "systems": [
    "LHS 1234"
  ]
}
```


#### 2.2.3. Player’s Current System

**Method:** GET  
**Path:** `/api/systems/current`

**Purpose**

Returns the current system and (if applicable) station, as tracked by the assistant’s system tracker.

**Response Example**

```json
{
  "system_name": "LHS 1234",
  "station_name": "Example Depot",
  "is_docked": true
}
```

Typical usage:

- Auto-select the current system in the shard
- Optionally show whether the player is docked and where


### 2.3. Per-System Colonisation Data

These endpoints operate on a **single system** and are useful for building a per-system view in the shard.


#### 2.3.1. Get All Sites in a System

**Method:** GET  
**Path:** `/api/system`  
**Query Parameters:**

- `name` (required, string): system name, for example `LHS 1234`

**Purpose**

Returns colonisation data for a single system, including its construction sites and overall progress.

**Response Example (simplified)**

```json
{
  "system_name": "LHS 1234",
  "construction_sites": [
    {
      "market_id": 123456,
      "station_name": "Example Depot",
      "station_type": "Outpost",
      "system_name": "LHS 1234",
      "system_address": 1234567890,
      "construction_progress": 42.5,
      "construction_complete": false,
      "construction_failed": false,
      "commodities": [
        {
          "name": "water",
          "name_localised": "Water",
          "required_amount": 1000,
          "provided_amount": 250,
          "remaining_amount": 750,
          "progress_percentage": 25.0,
          "payment": 250000,
          "status": "in_progress"
        }
      ],
      "total_commodities_needed": 750,
      "commodities_progress_percentage": 25.0,
      "last_updated": "2025-01-01T12:00:00Z",
      "last_source": "journal"
    }
  ],
  "total_sites": 1,
  "completed_sites": 0,
  "in_progress_sites": 1,
  "completion_percentage": 0.0
}
```


#### 2.3.2. Get a Single Site by Market ID

**Method:** GET  
**Path:** `/api/sites/{market_id}`

**Purpose**

Returns full details for a single construction site, identified by its market ID. This is useful if the shard deep-links to one specific depot.

**Response Example (simplified)**

```json
{
  "site": {
    "market_id": 123456,
    "station_name": "Example Depot",
    "system_name": "LHS 1234",
    "commodities": [
      {
        "name": "water",
        "name_localised": "Water",
        "required_amount": 1000,
        "provided_amount": 250,
        "remaining_amount": 750,
        "progress_percentage": 25.0,
        "payment": 250000,
        "status": "in_progress"
      }
    ],
    "total_commodities_needed": 750,
    "commodities_progress_percentage": 25.0
  }
}
```


### 2.4. Shopping List (Aggregated Commodities)

This is the primary endpoint for building a **per-system shopping list of commodities** in a GameGlass shard.

**Method:** GET  
**Path:** `/api/system/commodities`  
**Query Parameters:**

- `name` (required, string): system name

**Purpose**

Returns an **aggregated view of commodities** required across all construction sites in the specified system.

**Response Example**

```json
{
  "commodities": [
    {
      "commodity_name": "water",
      "commodity_name_localised": "Water",
      "total_required": 1000,
      "total_provided": 250,
      "total_remaining": 750,
      "average_payment": 250000,
      "sites_requiring": [
        "Example Depot",
        "Another Depot"
      ],
      "progress_percentage": 25.0
    }
  ]
}
```

Key fields for a shard:

- `commodity_name_localised`: display name
- `total_remaining`: how much the commander still needs to deliver
- `average_payment`: indicative payment per unit
- `sites_requiring`: which depots need this commodity
- `progress_percentage`: overall progress towards the total requirement

**Typical usage in a shard**

- For the **current system**:
  1. Call `/api/systems/current` to obtain `system_name`.
  2. Call `/api/system/commodities?name=<system_name>`.
  3. Render a list of rows with:
     - Commodity name
     - Remaining quantity
     - Payment information
     - List of depots requiring it (optional)

- For a **manually selected system**:
  1. Populate a system selector from `/api/systems`.
  2. When a system is chosen, call `/api/system/commodities?name=<selected_system>` and render as above.

If you want a **global shopping list** across **all systems**, there is no dedicated endpoint. Instead:

1. Call `/api/sites`.
2. Aggregate the `commodities` arrays from all `in_progress_sites` on the client (in the shard) to compute global totals.


### 2.5. Supporting Endpoints

These endpoints are useful for diagnostics and auxiliary UI, but are not strictly required for a basic construction-site-and-shopping-list shard.


#### 2.5.1. Health Check

**Method:** GET  
**Path:** `/api/health`

**Purpose**

Returns the health status of the assistant.

**Response Example**

```json
{
  "status": "healthy",
  "version": "2.3.1",
  "journal_directory": "C:\\\\Users\\\\Example\\\\Saved Games\\\\Frontier Developments\\\\Elite Dangerous",
  "journal_accessible": true
}
```

Typical usage:

- Verify that the backend is running before attempting other calls
- Show a small status indicator in the shard (optional)


#### 2.5.2. Journal Status

**Method:** GET  
**Path:** `/api/journal/status`

**Purpose**

Provides a minimal view of the latest journal-derived system.

**Response Example**

```json
{
  "current_system": "LHS 1234"
}
```

This can act as a fallback for inferring the current system directly from journal logs, but `/api/systems/current` is the richer endpoint if available.


#### 2.5.3. Settings

**Method:** GET  
**Path:** `/api/settings`

Returns the current application settings, including the journal directory and Inara configuration.

**Method:** POST  
**Path:** `/api/settings`

Accepts an updated settings object in JSON format. These endpoints are typically managed by the main web UI rather than a GameGlass shard, but they are listed here for completeness.


#### 2.5.4. Overall Statistics (Optional)

**Method:** GET  
**Path:** `/api/stats`

**Purpose**

Returns overall statistics about colonisation data stored in the assistant. This can be used for high-level summary panels in a shard (for example totals of sites, systems, etc.). Exact contents may evolve with the backend and can be inspected via the generated OpenAPI docs (`/docs` route) or by calling the endpoint directly.


## 3. Real-Time-ish Updates via AJAX long-poll

For a more responsive shard you can long-poll for changes instead of (or in addition to) periodically polling REST endpoints.

**URL:** `http://localhost:<port>/api/changes/longpoll`

### 3.1. Long-poll contract

Call:

`GET /api/changes/longpoll?since=<seq>&timeout_s=<seconds>`

Response shape:

```json
{
  "seq": 42,
  "changed": true
}
```

Client behavior:

- Keep a local `seq` (start at `0`).
- Loop forever:
  - Call long-poll with your current `seq`.
  - Update your local `seq` from the response.
  - If `changed` is `true`, refetch the REST endpoints you display (e.g. `/api/system?name=...`, `/api/system/commodities?name=...`).
  - If `changed` is `false` (timeout), simply long-poll again.


## 4. Recommended Integration Flow for a Shard

A typical GameGlass shard that wants to show **construction sites** and a **shopping list of commodities** might:

1. **On load**
   - Call `/api/health` to confirm the backend is running.
   - Call `/api/systems/current` to determine the commander’s current system.
   - Optionally, call `/api/systems` to populate a system selector.

2. **For the selected system**
   - Call `/api/system?name=<system_name>` to display per-site cards.
   - Call `/api/system/commodities?name=<system_name>` to build the aggregated **shopping list** for that system.

3. **Optional: live updates**
   - Long-poll `GET /api/changes/longpoll?since=<seq>`.
   - When it returns with `changed: true`, refetch the relevant REST endpoints.

4. **When the shard is closed or the system changes**
   - No unsubscribe required; just stop your long-poll loop.

This API-focused description is intended to be sufficient for shard authors to integrate with the ED Colonisation Assistant without needing to inspect the backend code.

---

## 5. Fleet carrier APIs (optional)

These endpoints expose the commander’s Fleet carrier data derived from Elite: Dangerous journal files. They are **optional** for GameGlass shards – use them if you want to display carrier cargo and market orders in addition to colonisation data.

Fleet carrier state is reconstructed in memory from `CarrierLocation`, `CarrierStats` and `CarrierTradeOrder` events by the backend logic in [`carrier_service.py`](backend/src/services/carrier_service.py:1) and surfaced via the carrier API routes in [`carriers.py`](backend/src/api/carriers.py:60).

### 5.1. Current docking context

**Method:** GET
**Path:** `/api/carriers/current`

**Purpose**

Returns whether the commander is currently docked at a Fleet carrier, and if so, basic identity information for that carrier.

**Response Shape (simplified)**

Based on [`CurrentCarrierResponse`](backend/src/models/api_models.py:129):

```json
{
  "docked_at_carrier": true,
  "carrier": {
    "carrier_id": 3700569600,
    "market_id": 3700569600,
    "name": "MIDNIGHT ELOQUENCE",
    "callsign": "X7J-BQG",
    "docking_access": "squadron",
    "allow_notorious": true,
    "last_seen_system": "Lupus Dark Region BQ-Y d66",
    "last_seen_station": "X7J-BQG",
    "services": [
      "dock",
      "commodities",
      "refuel",
      "repair",
      "rearm",
      "outfitting",
      "carrierfuel"
    ],
    "role": "own"
  }
}
```

Notes:

- If `docked_at_carrier` is `false`, `carrier` will be `null`.
- `services` is useful for displaying what is available at the current carrier.

Typical usage in a shard:

- Show a header indicating whether the commander is on a carrier and, if so, its name and callsign.
- Use the `carrier_id` / `market_id` to correlate with `/api/carriers/mine`.

### 5.2. Current carrier state snapshot

**Method:** GET
**Path:** `/api/carriers/current/state`

**Purpose**

Returns a reconstructed snapshot of the Fleet carrier the commander is currently docked at, including:

- Identity
- Cargo snapshot
- Buy and sell orders
- Basic cargo and capacity metrics
- Carrier capacity breakdown (when available)

**Response Shape (simplified)**

Based on [`CarrierStateResponse`](backend/src/models/api_models.py:144) and [`CarrierState`](backend/src/models/carriers.py:1):

```json
{
  "carrier": {
    "identity": {
      "carrier_id": 3700569600,
      "market_id": 3700569600,
      "name": "MIDNIGHT ELOQUENCE",
      "callsign": "X7J-BQG",
      "docking_access": "squadron",
      "allow_notorious": true,
      "last_seen_system": "Lupus Dark Region BQ-Y d66",
      "last_seen_station": "X7J-BQG",
      "services": [
        "dock",
        "commodities",
        "refuel",
        "repair",
        "rearm",
        "outfitting",
        "carrierfuel"
      ],
      "role": "own"
    },
    "cargo": [
      {
        "commodity_name": "fruitandvegetables",
        "commodity_name_localised": "Fruit and Vegetables",
        "stock": 9,
        "reserved": 0,
        "capacity": 2302
      }
    ],
    "buy_orders": [
      {
        "commodity_name": "fruitandvegetables",
        "commodity_name_localised": "Fruit and Vegetables",
        "price": 25,
        "original_amount": 9,
        "remaining_amount": 9
      }
    ],
    "sell_orders": [],
    "total_cargo_tonnage": 2302,
    "total_capacity_tonnage": 25000,
    "free_space_tonnage": 19328,
    "space_usage": {
      "total_capacity": 25000,
      "crew": 3370,
      "module_packs": 0,
      "cargo": 2302,
      "cargo_space_reserved": 9,
      "free_space": 19328
    }
  }
}
```

Key fields for a shard:

- `identity.name` / `identity.callsign`: for the carrier header.
- `cargo[*].commodity_name_localised`, `stock`, `capacity`: for a simple cargo panel.
- `buy_orders` / `sell_orders`:
  - `commodity_name_localised` – display name.
  - `price` – CR/t.
  - `remaining_amount` / `original_amount` – order fill progress.
- `space_usage`: (when present) the authoritative carrier capacity breakdown from `CarrierStats.SpaceUsage`.
  - Shards that want a single “free after buy orders” number can compute:
    - `space_usage.free_space` (already accounts for reserved buy space), or
    - `space_usage.total_capacity - space_usage.crew - space_usage.module_packs - space_usage.cargo - space_usage.cargo_space_reserved`

If the commander is not docked at any Fleet carrier, the backend returns a 404 error `"Commander is not currently docked at a fleet carrier"`; shards should handle this by hiding or disabling carrier panels.

### 5.3. Listing own and squadron carriers

**Method:** GET
**Path:** `/api/carriers/mine`

**Purpose**

Returns the commander's own carriers and (where detectable) squadron carriers, inferred from `CarrierStats` and `CarrierLocation` events across a window of recent journal files.

**Response Shape (simplified)**

Based on [`MyCarriersResponse`](backend/src/models/api_models.py:156):

```json
{
  "own_carriers": [
    {
      "carrier_id": 3700569600,
      "market_id": 3700569600,
      "name": "MIDNIGHT ELOQUENCE",
      "callsign": "X7J-BQG",
      "docking_access": "squadron",
      "allow_notorious": true,
      "last_seen_system": "Lupus Dark Region BQ-Y d66",
      "last_seen_station": "X7J-BQG",
      "services": [
        "dock",
        "commodities",
        "refuel",
        "repair",
        "rearm",
        "outfitting",
        "carrierfuel"
      ],
      "role": "own"
    }
  ],
  "squadron_carriers": [
    {
      "carrier_id": 1234567890,
      "market_id": 1234567890,
      "name": "SQUADRON CARRIER",
      "callsign": "AB1-CDE",
      "docking_access": "squadron",
      "allow_notorious": false,
      "last_seen_system": "LHS 1234",
      "last_seen_station": "AB1-CDE",
      "services": [
        "dock",
        "commodities"
      ],
      "role": "squadron"
    }
  ]
}
```

Typical usage in a shard:

- Render a list of your carriers (own and squadron).
- Highlight the carrier you are currently docked at by matching `carrier_id` / `market_id` against `/api/carriers/current`.
- Optionally show `last_seen_system` and `services` for each carrier.

### 5.4. Recommended Fleet carrier flow for a shard

For a GameGlass shard that wants to display **Fleet carrier state** alongside colonisation data:

1. **On load**
   - Call `/api/health` to confirm the backend is running.
   - Optionally call `/api/carriers/mine` to list known carriers.

2. **When docked at a carrier**
   - Call `/api/carriers/current` to check if `docked_at_carrier` is `true` and to get the carrier’s identity.
   - If docked, call `/api/carriers/current/state` to get cargo and market orders and render a carrier panel.

3. **When the commander undocks or moves**
   - Handle the 404 from `/api/carriers/current/state` as “not docked at a Fleet carrier” and hide carrier‑specific panels in the shard.

Carrier data is derived from local journals. EDCA parses a window of recent `Journal.*.log` files, and may also use `Market.json` as a snapshot source when carrier trade-order journal lines are missing or partial.
