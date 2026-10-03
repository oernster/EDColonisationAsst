# Decisions and trade-offs

The deliberate choices EDCA rests on: what was chosen, what was given up for
it and why. Each entry is the decision as the product makes it today. The
detail behind each one, with the tests that hold it, lives in
[ARCHITECTURE.md](ARCHITECTURE.md) and its two companions
([ARCHITECTURE_1_backend.md](ARCHITECTURE_1_backend.md),
[ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md));
[TESTING.md](TESTING.md) describes the gate; [TECH_DEBT.md](TECH_DEBT.md)
holds what only looks like debt.

## The product as a whole

### The journals are the only source

Everything EDCA shows is read from the journal files Elite Dangerous writes on
the commander's own machine, plus the companion market export beside them.

- **Rather than:** a community database or a web service such as Inara.
- **Gains:** no account, no key and no server; it works with the network
  switched off; what it shows is what the game itself recorded.
- **Costs:** it sees one commander's contributions only. Squadron-wide or
  shared tracking is out of reach; nothing happens when the game is not
  writing journals.

### Inara kept dormant rather than half working

The Inara integration is still in the code but makes no request and always
returns nothing, so every view is built from local journals alone. Its merge
rules are kept as the contract a future integration would have to meet.

- **Rather than:** a live integration built on events that do not carry
  construction data. An earlier attempt used community-goal events, which are
  unrelated and produced misleading errors and logs.
- **Gains:** no wrong data and no misleading failures; the seam is ready if a
  suitable event ever appears.
- **Costs:** unused configuration and state sit in the code; completed sites
  that only another source knows about are not shown.

### A web page served from the player's own machine

The interface is a web page the backend serves locally. A packaged install
has no window of its own: a tray icon opens the page in the browser.

- **Rather than:** a desktop window.
- **Gains:** the same page can be read from a tablet or phone beside the
  cockpit while the game has the screen.
- **Costs:** a browser is needed; reaching it from another device needs the
  firewall opened; the tray is the only thing on the desktop.

### LGPL-3.0

EDCA is free software under the GNU Lesser General Public Licence. It is free
with no paid tier; donations are invited, never required.

- **Rather than:** a stronger copyleft or a permissive licence.
- **Gains:** aligned with the Qt libraries the desktop parts are built on.
- **Costs:** none recorded.

## Privacy and the network

### One outbound request: the update check

Apart from probes it sends to itself, the only request EDCA makes is an
anonymous one to the public GitHub releases API asking what the latest version
is. It uses the standard library rather than an HTTP client package.

- **Rather than:** telemetry, an account or a second library for one request.
- **Gains:** nothing about the commander, the machine or the journals leaves
  the computer; the shipped runtime needs no import for the check.
- **Costs:** no usage figures; the release server cannot tell which versions
  are in use.

### The tray owns the update check; the web page has none

The tray checks once per run, three seconds after it starts. It says nothing
unless there is a newer release. A skipped version is not raised again. Help
then Check for Updates always answers, whatever the outcome. The offer is the
download for the platform it runs on: the installer on Windows, the Flatpak
bundle on Linux.

- **Rather than:** a check in the web page as well. The page is often read on
  a tablet, so it offered a Windows installer to devices that could not run
  it; two checks also meant one release could raise two prompts, each with a
  skip the other could not see.
- **Gains:** the offer appears on the machine that can act on it, once.
- **Costs:** someone who only ever looks at the web page is not told; there is
  no repeating timer, so a session left running for days hears nothing new
  until the next launch.

### Only the development server may read the API from another site

The list of browser origins allowed to call the backend holds the Vite
development server alone. The project's own website never called it and is
not on the list.

- **Rather than:** granting origins that might one day be useful.
- **Gains:** every entry on the list is a real caller; no other site's page
  can read the commander's data through the browser.
- **Costs:** a new browser client from another origin needs adding by hand.

### Served on every interface by default

The backend binds to all network interfaces, so a tablet on the same network
can open the page.

- **Rather than:** the loopback address alone.
- **Gains:** the tablet use the product is designed around works without a
  configuration change.
- **Costs:** anyone on the local network who can reach the port can read the
  page and change its settings, the journal folder included; there is no
  sign-in. EDCA is not meant to be exposed to the internet and says so.

### Requests must name this machine; writes must come from its own page

Every request must carry a Host that is an IP address, `localhost` or this
machine's own name; a write that names an Origin must be the page's own or a
configured CORS origin.

- **Rather than:** answering any Host and any Origin. A web page can rebind its
  own domain to 127.0.0.1 and then read everything, CORS being no defence for
  a page the browser thinks is same-origin; a bodiless cross-origin POST needs
  no preflight, so any site could make EDCA wipe and rebuild its database.
- **Gains:** neither attack works; the tablet still reaches the page by the
  PC's LAN address.
- **Costs:** a name that is not this machine's own (a hosts-file alias, say)
  is refused. Nothing here authenticates a LAN peer.

## Reading the journals

### The journal folder is found, not configured

On first use the journal folder is worked out from the Saved Games folder and
the usual Steam and Proton locations. The tracked configuration names no path;
the Settings page can override the guess.

- **Rather than:** a path written into the configuration. The one that used to
  be there pointed at one machine's Linux Steam prefix; the old fallback
  contained a Windows shell variable Python never expands.
- **Gains:** a normal installation needs no setup at all.
- **Costs:** an unusual layout still needs the Settings page.

### UK event spellings only

The parser accepts the colonisation events under the spelling Frontier
writes. The z-spelled names are not accepted.

- **Rather than:** accepting both spellings. The game does not emit the second
  one; testing it would need a fabricated journal line.
- **Gains:** the parser accepts what the game writes and nothing it does not.
- **Costs:** none recorded.

### The commander's name and balance come from the journal

Every game session opens its journal with the commander's name and the credit
balance it loaded with. The header reads both from there; the name is no
longer a setting.

- **Rather than:** a name typed into Settings.
- **Gains:** nothing to set up; it can never disagree with the game.
- **Costs:** the balance shown is the one the session started with, because
  the journal records no running balance.

### Each file is read from where the last pass stopped

A journal is read in full the first time it is seen; after that only what the
game has appended is read. A half-written final line is kept and tried again
rather than parsed as broken. A file that has shrunk is treated as replaced and
read again from the start.

- **Rather than:** rereading the whole file on every change.
- **Gains:** a busy session costs only the new lines; the game writing
  mid-line never produces a parse error.
- **Costs:** the reader keeps a position and a buffer for every file.

### Notifications first, with polling behind them in shipped builds

Live updates come from the operating system's file notifications. Every
shipped build, the Windows install and the Flatpak alike, also polls the
newest journal several times a second and reads it when it has changed. A
source checkout does not poll.

- **Rather than:** notifications alone, which operating systems report
  inconsistently for a file the game keeps appending to; polling alone, which
  costs more and reacts later; deciding by whether the build was compiled,
  which left the safety net switched off in every build that ships, since
  none of them is.
- **Gains:** the page keeps following the journal when notifications miss an
  append or the watcher cannot start at all.
- **Costs:** a small, constant amount of work while EDCA runs; a developer
  running from source does not exercise the poller day to day, so the suite
  checks it under each shipped build's conditions instead.

### The first import happens in the background

On a first run every journal already on the machine is read once, while the
server is already answering. Later launches read only the newest three
journal files. The import hands control back between files.

- **Rather than:** importing before the server starts answering, which held
  the startup splash for minutes on every launch.
- **Gains:** the page is available at once; colonisation history fills in as
  it is read.
- **Costs:** the first moments of a first run show an incomplete history.

### The first import is measured in bytes

The splash names the file being read and fills its bar by bytes read against
the total, from a list of every journal made before reading begins.

- **Rather than:** counting files, which made the bar lurch because journal
  files vary greatly in size; a single message for the whole import.
- **Gains:** the bar moves at something like a steady rate; the user can see
  the import is working.
- **Costs:** every journal is listed and sized before the first is read.

### The database is derived data

The colonisation database can always be rebuilt from the journals, so it runs
with the lighter durability setting and one shared connection. A database
whose schema version does not match is deleted and rebuilt rather than
migrated.

- **Rather than:** a full flush to disk on every commit and a connection per
  query; migrations between schema versions.
- **Gains:** measured on a real 72-file, 67 MB journal folder, the first import
  fell from 137.5 seconds to 2.2 and the longest stall of the server from
  137.4 seconds to under half a second, with an identical database.
- **Costs:** an operating system crash can lose the latest writes, at the
  price of one automatic rebuild; a schema change always means a full
  re-import.

## Colonisation

### Site progress from the deliveries themselves

A construction site's progress bar is the total delivered over the total
required across its commodities. A site with no requirements yet says it is
awaiting them.

- **Rather than:** the progress figure the journal records for the site,
  which can sit still while deliveries are happening.
- **Gains:** the bar moves when a delivery lands.
- **Costs:** the bar can differ from the game's own figure.

### Delivered amounts never go backwards

When a newer reading of a site arrives, each commodity keeps the larger of
the old and new amounts delivered and required.

- **Rather than:** taking the newest reading as it stands.
- **Gains:** a stale or partial reading cannot undo progress already seen.
- **Costs:** a genuine reduction would not be shown.

## Fleet carriers

### The hold is anchored on the market export

The game has no carrier inventory event. The hold is taken from the stock
column of the carrier's own market export, then carried forward by the
commander's own purchases and sales at the carrier. Any tonnage the result
cannot account for, against the carrier's own reported total, is shown rather
than hidden. A tonnage that falls below zero is dropped.

- **Rather than:** rebuilding the hold from transactions alone. Measured
  against 629 real readings of the carrier's total it matched none of them,
  drifting by up to 4,880 tonnes and producing negative holdings, because
  cargo also moves by routes the commander's journal never records.
- **Gains:** a hold that matches the carrier when the export is fresh; one
  that says how far it has drifted when it is not.
- **Costs:** the breakdown refreshes only when the commander docks at the
  carrier and opens its market; until then it shows its age.

### Holding and offering are two questions

What the carrier holds and what it has listed for sale are kept apart. The
hold covers every commodity aboard, whether or not an order is attached to it.

- **Rather than:** building the hold from sell orders, which made cargo with
  no order against it read as an empty hold.
- **Gains:** nothing aboard goes missing from the view.
- **Costs:** none recorded.

### A cancelled order stays cancelled

The market export replaces the orders the journal records only when it is the
newer of the two. A commodity cancelled after the export was written is
dropped from it; nothing brings an order back except a new one.

- **Rather than:** treating the export as authoritative whatever its age.
- **Gains:** an order the commander cancelled is no longer advertised.
- **Costs:** none recorded.

### A reading the journal did not carry is left out

Fuel, jump range, balances, tax rates and crew are shown only where the
journal stated them. A missing reading is omitted rather than shown as zero.

- **Rather than:** filling gaps with zeros or defaults.
- **Gains:** an empty gauge always means empty.
- **Costs:** a view can look sparse until the game writes the full figures.

### Balance movements carry no cause

The balance history lists every change in the carrier's balance across the
window the journals cover, with when and by how much. It never says why.

- **Rather than:** labelling movements as upkeep. The journal records no
  upkeep event; upkeep, tritium, crew changes and trade income all arrive as
  the same change of balance.
- **Gains:** nothing is invented.
- **Costs:** the commander cannot read an upkeep bill from it.

### A carrier is never docked

A carrier holds station in a system or has a jump booked. A booked jump names
its destination and counts down; it ends only on an arrival that matches the
destination system. A cancellation returns the carrier to holding station.

- **Rather than:** treating any later location report as arrival. The game
  writes one for the carrier's current system when the commander logs in,
  which would end a live jump early.
- **Gains:** the countdown stays true across a login.
- **Costs:** none recorded.

### Whether the commander is aboard is settled by the newest event

The newest docking, undocking, jump or location event decides whether the
commander is aboard. The carrier's own state is shown wherever the commander
is standing.

- **Rather than:** asking when the commander last docked at a carrier, which
  stayed true forever once it had happened.
- **Gains:** the panel no longer reports a commander aboard who has left; the
  hold is visible from anywhere.
- **Costs:** none recorded.

## The interface

### Live updates by long-poll

The page holds a request open to the backend; when the journals change the
request returns at once and the page fetches what changed.

- **Rather than:** the WebSocket push it replaced, which had not kept the
  interface up to date.
- **Gains:** one ordinary HTTP route that any browser can use, a GameGlass
  shard included.
- **Costs:** a request is always open; a client must loop.

### Keeping a tablet awake

The page can keep a tablet's screen on. It uses the browser's wake lock where
the page is in a secure context and a hidden looping video otherwise. It is on
by default on phones and tablets and remembered per browser.

- **Rather than:** asking the user to change the device's power settings.
- **Gains:** a tablet beside the cockpit stays lit through a long session.
- **Costs:** over plain HTTP on the local network the fallback needs one tap
  to start, because mobile browsers block it otherwise.

### One theme switch that shows its destination

The theme is a single control showing the theme a press will switch to,
remembered per browser.

- **Rather than:** two separate controls; an icon showing the current theme.
- **Gains:** one control, one convention.
- **Costs:** learned once.

### Dialogs from the tray stay on top

Every dialog the tray opens is set to stay on top before it is shown.

- **Rather than:** an ordinary modal dialog. With no main window to sit over,
  it opened behind a full-screen game, so Exit appeared to do nothing.
- **Gains:** the confirmation is seen when it is asked for.
- **Costs:** a dialog sits above the game until it is answered.

### A window when there is no tray

The application asks once, at start, whether the desktop has a tray. If it
does not, a small window offers the same actions and says why it is there.
Closing that window is the same as choosing Exit.

- **Rather than:** relying on a tray. Many Linux desktops have none, which
  left an application that could not be seen or quit except by killing it.
- **Gains:** there is always a way to open the page and to quit.
- **Costs:** the question is not asked again; a tray that appears later is not
  used.

## Running on the desktop

### An unusual port, then a short list, then any

The backend tries the port a previous run recorded, then the configured one,
then a short list of other known ports, then whatever
the operating system will give. The port chosen is recorded for next time. A
port Windows has reserved is told apart from one that is in use.

- **Rather than:** a fixed 8000. It fell inside a Windows reservation and could
  not be bound while nothing was listening on it; a random port each time.
- **Gains:** the page keeps an address a bookmark or a tablet can find; a
  reserved port no longer leaves the splash waiting on a backend that cannot
  start.
- **Costs:** the address is a preference, not a promise. A tablet user may
  have to read the port from the address bar.

### One copy per user

A lock file ensures one running copy per user. A second launch opens the page
of the copy already running and exits. On Windows the lock covers a fixed
region of the file; inside a Flatpak it lives in the one directory the sandbox
shares between instances.

- **Rather than:** letting copies race for the port.
- **Gains:** one backend, one tray; a repeated launch still does something
  useful.
- **Costs:** the lock needs care on each platform. Two earlier designs let
  two copies run: one on Windows, one inside a Flatpak.

### The browser opens only when the page will answer

The splash shows the icon, the version and a live status; the browser is
opened only once the backend and the page both respond. A start at sign-in
shows no splash and opens no browser. A backend that cannot start reports a
named cause rather than waiting out the timeout.

- **Rather than:** opening the browser at launch onto an empty page.
- **Gains:** the first page the user sees works.
- **Costs:** a short wait behind the splash.

### Packaged means a fixed layout, not a compiled one

The packaged behaviour (in-process server, tray, per-user data folder) is
chosen when the layout is fixed: inside a Flatpak or when the installed
launcher says so through an environment variable. Whether anything was
compiled does not decide it.

- **Rather than:** detecting a frozen executable, which neither the installed
  Windows build nor the Flatpak is.
- **Gains:** both packaged forms behave the same; nothing writes into a
  read-only install.
- **Costs:** the launcher must set the variable before anything is imported.

### One owner for where EDCA may write

A single function decides the per-user data folder: the local application
data folder on Windows, the XDG data folder elsewhere.

- **Rather than:** five places each deciding for themselves, all
  Windows-shaped. Inside a Flatpak they pointed into the read-only install, so
  the database could not be created.
- **Gains:** the database, the settings and the logs land somewhere writable
  on every platform; an existing Windows install keeps its database where it
  was.
- **Costs:** none recorded.

## Building and installing

### The application ships unfrozen

The installed Windows runtime is an ordinary Python interpreter with the
dependencies and EDCA beside it as readable source. Qt modules EDCA does not
use are removed from it.

- **Rather than:** a Nuitka-compiled executable. Malwarebytes quarantined the
  compiled runtime on sight wherever it sat; a rebuild with a newer Nuitka
  was flagged the same way. The same application shipped unfrozen scanned
  clean across 6,399 files. Pinning the compiled build's unpacking folder was
  tried first and did not solve it.
- **Gains:** nothing for a heuristic scanner to object to; anyone can read
  what runs. Removing the unused Qt modules saved a measured 471 MB.
- **Costs:** the source ships as written; the install holds thousands of
  files rather than one.

### The setup program is compiled and dependency-light

The setup program is a single compiled executable built with Nuitka. It
imports nothing from the application; it uses PySide6 and the standard library
alone, shelling out to the system's own tools to find and close a running
copy. The application travels inside it as one archive.

- **Rather than:** a generic installer; COM or a process library for process
  handling.
- **Gains:** one file to download; a small surface for the most privileged
  code in the product. Every external command goes through one replaceable
  seam, so tests spawn nothing.
- **Costs:** the setup program is EDCA's own to maintain.

### Installed for one user, without administrator rights

The install goes into the user's own folders and the current user's registry,
including the Apps and features entry and the optional start at sign-in.

- **Rather than:** a machine-wide install.
- **Gains:** no administrator prompt.
- **Costs:** each account on a machine installs separately.

### One pass for install, upgrade, reinstall and downgrade

Running the setup program over an existing install works out which of the four
it is, says so on its button and does it in one pass. A running copy is closed
only after the user agrees. A repair reads the sign-in setting back rather
than resetting it.

- **Rather than:** removing and reinstalling in two runs, which had left an
  upgrade uninstalled and not reinstalled.
- **Gains:** one button, one run, nothing lost.
- **Costs:** none recorded.

### Nothing written outside the install folder

Every file copied and every member extracted from the archive is checked to
land inside the install folder before it is written; links are skipped rather
than followed. A failed extraction stops the install; a missing archive leaves
a working install alone.

- **Rather than:** trusting the payload.
- **Gains:** a malformed archive cannot write elsewhere on the machine; a
  failure is never reported as success.
- **Costs:** none recorded.

### Closing the application ends only the application

When the setup program closes a running copy it ends that process alone, never
a process tree.

- **Rather than:** ending the tree, which could take the setup program itself
  down as a supposed descendant and reaped nothing, since the packaged runtime
  is one process.
- **Gains:** the setup program survives the close.
- **Costs:** none recorded.

### The uninstaller does not delete itself while running

What is registered as the uninstaller is a copy inside the install folder.
Whatever it cannot delete while running is handed to a detached helper that
waits until the files are released.

- **Rather than:** deleting in place, which failed silently because the
  uninstaller ran from inside the folder it was deleting.
- **Gains:** removal from Apps and features works.
- **Costs:** the last files go a moment after the window closes.

### Linux as a Flatpak, built offline

The Linux release is a Flatpak on the Freedesktop 25.08 runtime. The Python
wheels are downloaded on the host and installed inside the sandbox with no
network access. The sandbox may read and write the home folder, read a Flatpak
Steam's folder, use the network and talk to the desktop's tray service.

- **Rather than:** a package per distribution.
- **Gains:** one package for every distribution; a build that does not reach
  the network inside the sandbox.
- **Costs:** the home folder grant is broad, because the journals live inside
  a Wine or Proton prefix there; the Freedesktop runtime has to be fetched
  from Flathub on first install.

### The website versions its own files

The site's stylesheet link carries a hash of the file's content, so a browser
fetches a changed stylesheet at once. The version and download sizes are
read live from the releases API rather than written into the pages.

- **Rather than:** relying on cache expiry; stamping a version into the pages.
- **Gains:** a deployed page never pairs with an old stylesheet; the site
  never shows a stale version.
- **Costs:** the pages are rewritten by a script the runtime build runs; a
  change made without a build carries the old hash.

## Engineering

### Layers held by a structural test

The backend is split into models, repositories, services, the API and the
runtime, each importing only inwards. The setup program imports nothing from
the backend. A structural test reads the source and fails on any import that
breaks this, including one hidden inside a function.

- **Rather than:** convention alone.
- **Gains:** services can be tested with no database behind them; the setup
  program stays small.
- **Costs:** more modules and an interface with one implementation.

### Complete coverage where it means something

Statement and branch coverage must be total over the backend's models,
services, repositories, API and utilities, plus the setup program's Qt-free
half. The Qt shell and the two composition roots are excluded; anything worth
asserting is first moved out of them.

- **Rather than:** one figure over everything, which would need the Qt
  widgets faked.
- **Gains:** anything short of complete in the gated code is a decision
  nobody made.
- **Costs:** widget behaviour relies on manual checking and the packaged-build
  smoke test.

### Tests with real parts

No mocking library is used. Tests use real SQLite databases in temporary
folders, the ASGI test client for endpoints and hand-written fakes. The setup
program's tests write only to a scratch registry key and a temporary profile.
Most watcher tests use a fake file watcher; one starts the real one on a
temporary folder and fails unless a journal append reaches EDCA through it.

- **Rather than:** mocks; fakes everywhere. A watcher that fails to start is
  treated as non-fatal, so with fakes alone a library that cannot start on the
  shipped interpreter passed every test.
- **Gains:** a passing test means the real thing works; no test touches a real
  installation.
- **Costs:** fakes are written by hand; the real-watcher test waits on the
  filesystem rather than returning at once.

### Small modules

No Python or TypeScript file may exceed 400 lines. The two build scripts are
exempt as linear recipes.

- **Rather than:** letting files grow. Nineteen were over the limit when the
  rule arrived; each was split at a real seam until none was left.
- **Gains:** modules split where the code already divided.
- **Costs:** many small files.

### One definition for each shared value

The port and its fallback list are defined once, in a module that imports
nothing; everything else derives from them. The version comes from one
file.

- **Rather than:** copies where they are used. The port once had three
  separate hardcoded copies in Python alone; a constant placed elsewhere
  created a circular import that stopped the package loading.
- **Gains:** a change is made once and cannot drift.
- **Costs:** a module that must stay free of imports.

### A broad exception handler says why

Every exception handler that catches broadly and swallows the error has a
written reason; handlers that can be narrowed to the errors they can actually raise
are.

- **Rather than:** silent broad handlers.
- **Gains:** a reader can tell a deliberate catch from a careless one.
- **Costs:** more comment in the error paths.

### The commit hook runs the real gate

The pre-commit hook formats staged Python, lints the Python and the front end,
then runs the full suite under the coverage gate. It uses one interpreter for
every step, preferring the project's own environment; it stops with a named
error if that interpreter lacks any of the tools. Type checking and the
front-end test suite are left out of it.

- **Rather than:** a lighter check; one that silently runs without its tools.
- **Gains:** a commit cannot land below the gate; the check that runs is the
  one documented.
- **Costs:** each commit waits for the suite; front-end types and tests are
  checked separately.

### Front-end linting without types

The front end is linted from the plugins already installed, with no type-aware
rules; the TypeScript compiler checks types over the same files.

- **Rather than:** type-aware linting, which would trip over the test files
  the compiler configuration excludes.
- **Gains:** a fast lint that the hook can afford to run.
- **Costs:** type problems are caught only when the compiler is run.
