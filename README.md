# <img width="64" height="64" alt="edcolonisationasst-icon" src="https://github.com/user-attachments/assets/f840c1d9-f120-448d-ae1c-43dbc6cf0d8a" /> Elite Dangerous Colonisation Assistant (EDCA)

## Designed for players actively working on colonisation sites and fleet carrier logistics.

Track colonisation sites and fleet carrier activity automatically from your journal files.

No spreadsheets. No manual tracking. Runs locally.

---

### What it does

Replaces manual tracking with automatic, journal-driven state.

- Tracks colonisation construction sites directly from your journal data  
- Shows what your fleet carrier is actually holding, commodity by commodity  
- Shows fleet carrier buy and sell orders in one place  
- Updates automatically as you play  
- Runs entirely locally (no external services, no accounts) 

### Who it is for and who it is not for

It is for a commander running colonisation build-outs on PC who is tired of
keeping a spreadsheet beside the cockpit and who is happy with a browser tab
or a tablet on the same network as their HUD.

It is not for you if you want squadron-wide or shared tracking: Elite
Dangerous writes journals per player on the local machine, so EDCA can only
ever see your own contributions and does not pretend otherwise. It is also
Windows-only as a packaged release (a source checkout runs on Linux; see
below); it does nothing at all when the game is not writing journals.

---

<img width="1582" height="1248" alt="{D494D007-E38F-465D-9AF5-BF34A431AEF3}" src="https://github.com/user-attachments/assets/9b73bf79-8524-4c58-bd9e-ae8e70fc08ec" />
<img width="1581" height="1180" alt="{173686A9-ADF6-4BC7-A637-A72F629DFEF4}" src="https://github.com/user-attachments/assets/e52917a0-dc5f-4938-b708-5151eb1f7060" />

---

## Quick start (Windows)

1. Go to the project’s **Releases** page
2. Download the latest installer:
   EDColonisationAsstInstaller.exe
3. Run it and follow the installer
4. Launch **Elite: Dangerous Colonisation Assistant**

Your browser will open automatically at:

http://127.0.0.1:8000/app/

EDCA will begin reading your journal files immediately.

### Upgrading and removing

Run the same installer over an existing installation: it works out whether
that is an upgrade, a reinstall or a downgrade, says which on its button and
does it in one pass. If EDCA is running it offers to close it first, telling
you plainly that the running session ends.

To remove EDCA, use **Apps & features** (Add/Remove Programs) rather than the
downloaded installer. That is the registered uninstaller; it cleans up the
install directory, the shortcuts and the sign-in entry.

---

## Fleet carrier data and journal updates

EDCA's Fleet Carrier view (the hold plus market orders) is built from your local Elite Dangerous journal data.

Internally, EDCA:

- Parses a **window of recent** `Journal.*.log` files (not just the single newest file), because carrier-related events are not guaranteed to be present in the latest journal.
- Reconstructs carrier identity/state primarily from `Docked`, `CarrierLocation`, `CarrierStats` and `CarrierTradeOrder` events.
- Uses `Market.json` as a **snapshot source** for carrier market configuration when the journal only contains partial `CarrierTradeOrder` updates (or none at all).

This has two important consequences:

* If you change your carrier's market in-game but the game does **not** emit new journal events (such as `CarrierTradeOrder` entries) **and** `Market.json` is not updated, EDCA cannot see that change and the UI will continue to show the last state it can derive locally.
* To ensure EDCA shows valid, up-to-date carrier commodity data, you may occasionally need to:

  * Open the Carrier Management screen and adjust or re-apply your commodity orders (even if only by toggling/cancelling and re-creating them), so that the game writes fresh carrier trade events to the journal.
  * Wait a moment for the journal watcher to ingest the new lines and for the UI to refresh.

EDCA cannot force Elite Dangerous to write new journal data; it can only reflect what is actually present in your local `Journal.*.log` files.

> **Tip:** The Fleet Carrier UI uses the carrier capacity breakdown from `CarrierStats.SpaceUsage` when available (TotalCapacity, Crew/ModulePacks usage, Cargo usage and reserved space for buy orders).

### What the carrier is holding

The game emits no carrier inventory event, so the **Cargo** tab derives one. The per-commodity hold is anchored on the `Stock` column of your carrier's own market export, which is the real hold rather than only what you have listed for sale. It is then carried forward by your own purchases and sales against the carrier.

Two things follow from that:

- The breakdown only refreshes when you **dock at the carrier and open its commodity market**, because that is when the game rewrites the export. The tab shows how old that reading is rather than presenting it as live.
- Cargo can also move by routes your journal never records, for example another commander trading at your carrier. `CarrierStats` reports the carrier's own total independently, so where that total disagrees with the summed breakdown, the tab reports the difference instead of quietly showing a wrong number.

> **Note:** Because this is not a code‑signed commercial product, Windows SmartScreen
> (and some antivirus tools) may warn that the installer or runtime is from an
> unrecognised publisher. If you are unsure, you can always review the complete
> source code in this repository to reassure yourself before choosing to run the
> installer.

## Run on Linux

If you are running EDCA from a local checkout on Linux, use the helper script from the project root:

```bash
chmod +x ./run-edca-built.sh
./run-edca-built.sh
```

It detects your package manager (apt, dnf, pacman, zypper, xbps, apk or yum) and phrases any
install hint it needs to print in that distribution's own idiom. Nothing is installed for you
and no privileged command is run. Debian, Ubuntu and Linux Mint are the tested path; the others
are **UNTESTED** but take the same route.

The script:

- Sets up a Python virtual environment and backend runtime dependencies.
- Ensures the frontend is built (or lets you skip the build via environment variables).
- Starts the backend on `http://127.0.0.1:8000`.
- Opens your browser at `http://127.0.0.1:8000/app/`.

For full Linux prerequisites and advanced usage (including environment variables and alternative workflows), see [`DEVELOPMENT-README.md`](DEVELOPMENT-README.md).

The installed runtime starts a local web server and opens your browser to:

```text
http://127.0.0.1:8000/app/
```

---

## Elite Dangerous journal log location

EDCA reads **Elite Dangerous journal files** directly from your local save folder. On a default Windows installation of the game (non‑Horizons4), the journals are typically located at:

```text
C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous
```

If you run Elite via Steam Proton or Wine on Linux, the journal directory is usually under your Proton/Wine prefix, for example:

```text
~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous
```

You can point EDCA at a different journal directory via the Settings page in the web UI (`Journal directory` field). The backend will monitor whatever path is configured there for `Journal.*.log` files.

---

## Access from a tablet or phone on the same network

You can open the EDCA UI from another device (for example, a tablet) as long as:

- The PC running EDCA and the tablet/phone are on the **same local network** (Wi‑Fi/LAN).
- Your firewall allows local access to port `8000` on the PC.

### 1. Find your PC’s LAN IP address (Windows)

On the Windows PC where EDCA is installed:

1. Press `Win + R`, type `cmd` and press Enter to open Command Prompt or open PowerShell.
2. Run:

   ```text
   ipconfig
   ```

3. Find your active network adapter (for example `Wi‑Fi` or `Ethernet`).
4. Under that adapter, look for the line:

   ```text
   IPv4 Address . . . . . . . . . . : 192.168.1.238
   ```

   The `192.168.x.x` (or `10.x.x.x`) value is your **LAN IP**.

### 2. Use that IP on your tablet/phone (local network only)

On your tablet/phone (connected to the same Wi‑Fi/LAN):

1. Open a browser (Chrome, Edge, Safari, etc.).
2. Enter the following URL, replacing `<PC-LAN-IP>` with the IPv4 address you found:

   ```text
   http://<PC-LAN-IP>:8000/app/
   ```

   Example:

   ```text
   http://192.168.1.238:8000/app/
   ```

This works **only on your local network**; EDCA is not intended to be exposed directly to the internet.

### Keep the tablet screen awake (Android/Chrome)

If your tablet dims/turns off the screen during long viewing sessions, EDCA provides an **in-browser keep-awake** feature.

- Enable it in [`Settings`](frontend/src/components/Settings/SettingsPage.tsx:1) → **Display / Power** → “Keep screen awake while EDCA is open”.
- Default behaviour: **ON** by default on mobile/tablet devices (can be turned off; it persists in `localStorage`).

How it works:

1. **Preferred**: Screen Wake Lock API (when supported).
   - Requires a **secure context** (HTTPS or `localhost`).
2. **Fallback** (for typical LAN access over HTTP like `http://<PC-LAN-IP>:8000/app/`):
   - EDCA uses a safe fallback that requires a **single tap** to start (mobile autoplay restrictions).

The current state is shown in the header via the “Keep awake” indicator in [`App()`](frontend/src/App.tsx:63).

---

## Development / source checkout

### What it is built with

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, uvicorn, SQLite, watchdog |
| Frontend | React + TypeScript, Vite, MUI, Zustand |
| Live updates | AJAX long-poll (`/api/changes/longpoll`) |
| Desktop runtime | PySide6 tray and splash around an in-process uvicorn |
| Setup program | A separate PySide6 application, standard library only besides Qt |
| Packaging | Nuitka onefile, one EXE for the runtime and one for the installer |
| Tests | pytest with a 100% statement and branch gate, vitest for the frontend |

### The three commands

```bash
python -m pytest -q     # whole gated suite: backend + setup program (from the root)
python buildexe.py      # build the runtime EXE
python buildinstaller.py # stage the payload and build the installer EXE
```

### Licence

EDCA is free software under the GNU Lesser General Public Licence v3.0; see
[`LICENSE`](LICENSE).

### The documentation set

If you have cloned the repository and want to build or run EDCA from source, the documentation set is:

- [`DEVELOPMENT-README.md`](DEVELOPMENT-README.md) - how to build the Windows release (`python buildexe.py` then `python buildinstaller.py`), run the backend and frontend from source and set up the dev environment
- [`TESTING.md`](TESTING.md) - how to run the test suites (`python -m pytest -q` from the root, with a 100% coverage gate over the backend and the Qt-free half of the setup program)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - high-level system and component design
- [`TECH_DEBT.md`](TECH_DEBT.md) - what is still open, what is deliberately left and what only looks like debt
- [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md) - backend architecture in detail
- [`ARCHITECTURE_2_frontend_and_runtime.md`](ARCHITECTURE_2_frontend_and_runtime.md) - frontend and packaged-runtime architecture
- [`PROJECT_SETUP.md`](PROJECT_SETUP.md) - first-time environment setup notes
- [`GameGlass-Integration.md`](GameGlass-Integration.md) - GameGlass shard integration

Elite Dangerous is a trademark of Frontier Developments plc. This tool is not affiliated with Frontier. 
