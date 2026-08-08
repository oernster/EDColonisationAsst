# <img width="128" height="128" alt="EDColonisationAsst" src="https://github.com/user-attachments/assets/94129dab-d96b-4bf2-8d42-bac5c1fe933f" /> Elite Dangerous Colonisation Assistant (EDCA)

**For commanders actively working on colonisation sites and fleet carrier logistics.**

Track colonisation sites and fleet carrier activity automatically from your
journal files. No spreadsheets. No manual tracking. Runs locally.

---

## What it does

Replaces manual tracking with automatic, journal-driven state.

- Tracks colonisation construction sites directly from your journal data
- Shows what your fleet carrier is actually holding, commodity by commodity
- Shows fleet carrier buy and sell orders in one place
- Reports what the carrier runs on: fuel and jump range, balance and tax rates,
  the balance movements over time and who is crewing each service
- Says when the carrier has a jump booked, where to and how long until it leaves
- Updates automatically as you play
- Runs entirely locally, with no external services and no accounts

## Who it is for and who it is not for

It is for a commander running colonisation build-outs on PC who is tired of
keeping a spreadsheet beside the cockpit and who is happy with a browser tab
or a tablet on the same network as their HUD.

It is not for you if you want squadron-wide or shared tracking: Elite Dangerous
writes journals per player on the local machine, so EDCA can only ever see your
own contributions and does not pretend otherwise. It is also Windows-only as a
packaged release (a source checkout runs on Linux; see
[Run from source on Linux](#run-from-source-on-linux)); it does nothing at all
when the game is not writing journals.

---

## Install and run (Windows)

1. Go to the project's **Releases** page
2. Download the latest installer: `EDColonisationAsstInstaller.exe`
3. Run it and follow the installer
4. Launch **Elite: Dangerous Colonisation Assistant**

Your browser will open automatically at:

```text
http://127.0.0.1:47021/app/
```

That is the usual address. The port is a preference rather than a promise: if
something else on the machine has taken it or Windows has reserved it, EDCA
serves on the next address it can bind and remembers it for next time. The tray
icon's **Open Web UI** always goes to the right one.

The first launch reads every journal already on your machine, once, so that you
start with the colonisation history you have actually flown rather than from
empty. The splash says so while it happens, naming the file it is on and how far
through it is. Later launches skip straight past it.

> **On SmartScreen warnings:** because this is not a code-signed commercial
> product, Windows SmartScreen (and some antivirus tools) may warn that the
> installer or runtime is from an unrecognised publisher. If you are unsure, you
> can review the complete source code in this repository before choosing to run
> the installer.

### Upgrading and removing

Run the same installer over an existing installation: it works out whether that
is an upgrade, a reinstall or a downgrade, says which on its button and does it
in one pass. If EDCA is running it offers to close it first, telling you plainly
that the running session ends.

To remove EDCA, use **Apps & features** (Add/Remove Programs) rather than the
downloaded installer. That is the registered uninstaller; it cleans up the
install directory, the shortcuts and the sign-in entry.

---

## Where EDCA reads your journals

EDCA reads **Elite Dangerous journal files** directly from your local save
folder. On a default Windows installation of the game (non-Horizons4), the
journals are typically at:

```text
C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous
```

If you run Elite via Steam Proton or Wine on Linux, the journal directory is
usually under your Proton or Wine prefix, for example:

```text
~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous
```

You do not have to tell EDCA where any of this is. It works the directory out
for itself from your Saved Games folder on first use, so a normal installation
needs no configuration at all. If yours is somewhere unusual, point EDCA at it
via the Settings page in the web UI (`Journal directory` field) and the backend
will monitor whatever path is configured there for `Journal.*.log` files
instead.

---

## What the Fleet Carrier view shows

The Fleet Carrier view (the hold, the market orders, what the carrier runs on
and where it is heading) is built from your local journal data. Where you are
standing does not change what your carrier is holding, so the view is shown
whether or not you are aboard and says plainly which of the two it is.

### What the carrier is holding

The game emits no carrier inventory event, so the **Cargo** tab derives one. The
per-commodity hold is anchored on the `Stock` column of your carrier's own
market export, which is the real hold rather than only what you have listed for
sale. It is then carried forward by your own purchases and sales against the
carrier.

Two things follow from that:

- The breakdown only refreshes when you **dock at the carrier and open its
  commodity market**, because that is when the game rewrites the export. The tab
  shows how old that reading is rather than presenting it as live.
- Cargo can also move by routes your journal never records, for example another
  commander trading at your carrier. The game reports the carrier's own total
  independently, so where that total disagrees with the summed breakdown, the
  tab reports the difference instead of quietly showing a wrong number.

### What the carrier runs on

The **Status** tab reports the carrier itself rather than its trade: tritium in
the tank with the current jump range against the maximum, the balance with its
reserve and the tax each service charges visitors, every movement in the balance
over the window it was observed and who is crewing each service.

A reading your journal has not carried is left out rather than shown as a zero,
so an empty gauge always means empty. The balance history attaches no cause to
any movement: the journal records no upkeep event; nothing in it separates
upkeep from a tritium purchase or from trade income.

### Where the carrier is going

A carrier is never docked. It holds station in a star system or it has a jump
booked and has not left yet. Booking a jump names the destination and counts
down to departure; the arrival clears the countdown; cancelling it returns the
carrier to holding station.

### If the carrier view looks out of date

EDCA reads a window of recent `Journal.*.log` files rather than only the newest,
because carrier events are not guaranteed to appear in the latest one. It also
uses `Market.json` as a snapshot source when the journal carries only partial
market updates. Even so, it can only reflect what the game has actually written.

So if you change your carrier's market in-game and the game emits no matching
journal events, EDCA keeps showing the last state it could derive. To prompt a
refresh:

1. Open the Carrier Management screen and adjust or re-apply your commodity
   orders, even if only by cancelling and re-creating them, so that the game
   writes fresh carrier events to the journal.
2. Give the journal watcher a moment to ingest the new lines and the UI a moment
   to refresh.

EDCA cannot make Elite Dangerous write journal data; it can only reflect what is
present in your local `Journal.*.log` files. The full ingestion pipeline is
documented in
[`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md).

---

## Use EDCA from a tablet or phone

You can open the EDCA UI from another device on your own network, as long as:

- The PC running EDCA and the tablet or phone are on the **same local network**
  (Wi-Fi or LAN).
- Your firewall allows local access to port `47021` on the PC.

### 1. Find your PC's LAN IP address

On the Windows PC where EDCA is installed:

1. Open Command Prompt or PowerShell: press `Win + R`, type `cmd` and press
   Enter.
2. Run:

   ```text
   ipconfig
   ```

3. Find your active network adapter (for example `Wi-Fi` or `Ethernet`).
4. Under that adapter, look for the line:

   ```text
   IPv4 Address . . . . . . . . . . : 192.168.1.238
   ```

   The `192.168.x.x` (or `10.x.x.x`) value is your **LAN IP**.

### 2. Open EDCA on the tablet or phone

On the tablet or phone, connected to the same network, open a browser and enter
the following, replacing `<PC-LAN-IP>` with the address you found:

```text
http://<PC-LAN-IP>:47021/app/
```

For example:

```text
http://192.168.1.238:47021/app/
```

This works **only on your local network**; EDCA is not intended to be exposed
directly to the internet.

If the page does not load, check which port EDCA actually chose rather than
assuming `47021`: open the UI from the tray icon on the PC and read the port out
of the address bar.

### Keeping the tablet screen awake

If your tablet dims or turns off the screen during a long session, EDCA has an
in-browser keep-awake option.

Enable it in **Settings** → **Display / Power** → "Keep screen awake while EDCA
is open". It is on by default on mobile and tablet devices, can be turned off
and persists in `localStorage`. The current state is shown by the "Keep awake"
indicator in the header.

Where the browser supports the Screen Wake Lock API it uses that, which requires
a secure context (HTTPS or `localhost`). For typical LAN access over plain HTTP
it falls back to a method that needs a single tap to start, because mobile
browsers block it otherwise.

---

## Run from source on Linux

There is no packaged Linux release. To run EDCA from a local checkout, use the
helper script from the project root:

```bash
chmod +x ./run-edca-built.sh
./run-edca-built.sh
```

The script:

- Sets up a Python virtual environment and the backend runtime dependencies.
- Ensures the frontend is built. Environment variables let you skip that step.
- Starts the backend on `http://127.0.0.1:47021`.
- Opens your browser at `http://127.0.0.1:47021/app/`.

It detects your package manager (apt, dnf, pacman, zypper, xbps, apk or yum) and
phrases any install hint it needs to print in that distribution's own idiom.
Nothing is installed for you and no privileged command is run. Debian, Ubuntu
and Linux Mint are the tested path; the others are **UNTESTED** but take the
same route.

For full Linux prerequisites and advanced usage, including environment variables
and alternative workflows, see
[`DEVELOPMENT-README.md`](DEVELOPMENT-README.md).

---

## Development

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
python -m pytest -q      # whole gated suite: backend + setup program (from the root)
python buildexe.py       # build the runtime EXE
python buildinstaller.py # stage the payload and build the installer EXE
```

### The documentation set

If you have cloned the repository and want to build or run EDCA from source:

- [`DEVELOPMENT-README.md`](DEVELOPMENT-README.md) - how to build the Windows
  release, run the backend and frontend from source and set up the dev
  environment
- [`TESTING.md`](TESTING.md) - how to run the test suites, with a 100% coverage
  gate over the backend and the Qt-free half of the setup program
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - high-level system and component design
- [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md) - backend
  architecture in detail
- [`ARCHITECTURE_2_frontend_and_runtime.md`](ARCHITECTURE_2_frontend_and_runtime.md) -
  frontend and packaged-runtime architecture
- [`TECH_DEBT.md`](TECH_DEBT.md) - what is still open, what is deliberately left
  and what only looks like debt
- [`PROJECT_SETUP.md`](PROJECT_SETUP.md) - first-time environment setup notes
- [`GameGlass-Integration.md`](GameGlass-Integration.md) - how a GameGlass shard
  or other embedded web view talks to the backend API

---

## Licence

EDCA is free software under the GNU Lesser General Public Licence v3.0; see
[`LICENSE`](LICENSE).

Elite Dangerous is a trademark of Frontier Developments plc. This tool is not
affiliated with Frontier.
