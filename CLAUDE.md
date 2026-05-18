# FTTH GIS Route Planner — Claude Code Context

> This file is read automatically by Claude Code every session.
> Keep it updated as the project evolves.

---

## What This Project Is

A professional-grade, multi-platform **Fiber-to-the-Home / Backhaul GIS route planning tool** built for field fiber technicians and network designers. It runs as a web app, PWA, Android/iOS app (Capacitor), and Windows/macOS/Linux desktop app (Electron).

The entire application logic lives in **`index.html`** (2,400+ lines of vanilla HTML/CSS/JS). There is no build step for the web version — open `index.html` in a browser and it runs.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Map | Leaflet.js 1.9.4 (CDN) | OpenStreetMap, Google Maps, Mapbox, Esri tiles |
| Language | Vanilla JS (ES2020) | No framework, no bundler for web |
| Mobile | Capacitor 6 | Wraps index.html → Android APK + iOS IPA |
| Desktop | Electron 31 | Wraps index.html → Win/Mac/Linux |
| Offline | Service Worker (sw.js) | Caches 3,000 map tiles + app shell |
| PWA | manifest.json + sw.js | Installable from any browser |
| Container | Docker + nginx Alpine | Self-hosted deployment |
| CI/CD | GitHub Actions | Builds all platforms on push |

---

## Project File Structure

```
ftth-app/
├── index.html              ← MAIN APP — all features here
├── manifest.json           ← PWA web manifest
├── sw.js                   ← Service worker (offline tiles)
├── CLAUDE.md               ← This file
├── package.json            ← npm: Capacitor + Electron + electron-builder
├── capacitor.config.ts     ← Capacitor iOS/Android settings
├── electron/
│   ├── main.js             ← Electron main process (menus, IPC, file dialogs)
│   └── preload.js          ← Context bridge (exposes saveFile, openFile to renderer)
├── assets/
│   └── icon*.svg           ← App icons (SVG, all sizes)
├── Dockerfile              ← nginx Alpine ~25MB container
├── nginx.conf              ← Production nginx with SW headers
├── DEPLOY.md               ← Full deployment instructions for all platforms
└── .github/workflows/
    └── build.yml           ← CI: builds Electron+Docker+Android on push
```

---

## What Has Been Built

### Core Map (index.html)

- **Leaflet map** with 8 tile layers: CartoDB Dark, OSM Street, Esri Satellite, OSM Topo, Google Satellite, Google Hybrid, Mapbox Satellite, Mapbox Satellite Streets
- **Mapbox token management** — modal to enter `pk.` token, stored in localStorage

### Infrastructure Placement

Place these node types by clicking the map (or GPS drop):

| ID | Label | Color | Notes |
|----|-------|-------|-------|
| `co` | Central Office | amber | OLT, GPON starting point |
| `cabinet` | Cabinet / FDH | blue | 1:4 PLC splitter |
| `odp` | ODP / FAT | purple | 1:8 PLC splitter |
| `closure` | Splice Closure | green | 0.1 dB loss |
| `patchpanel` | Patch Panel / ODF | pink | 0.5 dB loss |
| `manhole` | Manhole | slate | 0.5 dB loss |
| `customer` | Customer / ONT | cyan | End subscriber |
| `rack` | Rack / FTTB Room | teal | Indoor distribution |
| `tower` | Cell Tower / gNB | orange | Backhaul node |
| `pop` | PoP / Core Node | cyan2 | 50µs equipment latency |
| `edfa` | EDFA Amplifier | lime | −24 dB (gain!) |
| `dwdm` | DWDM Mux/Demux | rose | 3 dB loss, 5µs latency |
| `otn` | OTN Switch/Regen | violet | 100µs latency |

### Fiber Route Drawing

Five route types (click waypoints, double-click or Enter to finish):
- **Trench** (orange dashed) — direct bury
- **Conduit** (grey dashed) — in duct
- **Aerial** (blue solid) — self-supporting
- **Trussbore/HDD** (red dashed) — horizontal directional drilling
- **Underpass** (purple dashed) — road crossings

Route Properties Modal (appears after finishing a route):
- Cable spec from 25-entry library (1F bare buffer → 288F standard LT)
- Quantity (1–8 cables)
- Auto-computed fiber total
- Duct size (11 options: 10mm OD microduct → 160mm OD conduit)
- Live duct fill ratio with 53%/40% pass/fail rule
- Compare group (Route A / Route B)

### GPS Field Tool

Sidebar section for field use:
- `USE DEVICE GPS` button — calls `navigator.geolocation` (or native Capacitor plugin on mobile)
- Manual lat/lng coordinate input
- `DROP PIN AT COORDINATES` — places selected infrastructure type at those coords
- **Auto-Chain Mode** — toggle ON, then each dropped pin auto-connects to the previous pin with the selected route type. Walk the route, drop pins, routes draw themselves.
- Chain status shows the growing sequence: `ONT-001 → ONT-002 → ONT-003`

### Info Panel Tabs

**ELEMENTS** — grouped list of all placed infrastructure, click to pan/inspect, delete button

**ROUTES** — list of drawn routes with cable spec, fiber count, duct, distance; Route A vs B comparison table with editable $/m cost rates

**PON BUDGET** — PON/FTTH loss budget calculator:
- Select CO → ONT
- BFS path-finding through connected network
- Accumulates fiber loss (0.35 dB/km), splitter losses (FDH 7.2 dB, ODP 10.5 dB), connector/splice losses
- Pass/fail vs GPON −28 dBm threshold

**P2P/BHL** — Backhaul/P2P tab with four sub-panels:
- *Link Budget*: 12-entry transceiver library (SFP 1GE ZX → CFP2 400G DWDM), EDFA gain support, fiber grade selector
- *Latency*: fiber propagation (4.9 µs/km), per-node equipment delays, 3GPP 5G ≤100µs flag
- *Ring Analysis*: Route A = primary, Route B = protection; ring circumference, path diff, MSP 1+1
- *DWDM Channels*: 16-channel C-band grid (C1–C16), highlight channels in use via route label

**BoM** — Bill of materials:
- Fiber by route type with cost estimate
- Infrastructure count
- Materials list with 15% slack
- **Duct Fill Calculator**: standalone tool — select duct, add multiple cables with quantities, see fill ratio, remaining capacity, how many more cables fit

**SURVEY** — Site survey card for selected element:
- Pre-filled GPS, capacity, notes
- Interactive checklist (different items per node type)
- Check items off as you walk the site
- Print button → opens printable A4 card with sign-off lines

### Exports

- **GeoJSON** — all elements (Points) + routes (LineStrings) with full properties
- **KML** — Google Earth compatible, coloured by route/node type
- **CSV / BoM** — elements table + routes table + bill of materials summary

### Persistence

- **💾 SAVE** — writes entire design to `localStorage` as JSON
- **📂 LOAD** — restores design (elements + routes) from `localStorage`
- Auto-restores map centre and zoom level

---

## Key State Object

The main app state lives in `const S = { ... }` around line 730 in index.html:

```javascript
const S = {
  tool, toolKind, infraType,         // active tool
  drawing, pts, tempPoly, tempDots,  // route drawing state
  pendingLL, pendingType,            // queued infra placement
  elements[], routes[],              // placed data
  selElem,                           // selected element id
  snapTarget, snapRing,              // GPS snapping
  compareGroup,                      // 'none'|'A'|'B'
  pendingRoute,                      // route awaiting modal confirm
  activePanel,                       // info panel tab
  surveyChecks,                      // {elemId: Set<index>}
};
```

---

## Key Constants

```javascript
INFRA        — node types config (color, label, abbr, lossAdd, latUs)
ROUTES       — route types config (color, dash, weight, label)
TILES        — tile layer URLs (8 entries)
XCVR         — 12 transceiver specs for P2P link budget
DWDM_CH      — 16 ITU C-band channels
CABLES       — 25 fiber cable specs (name, fibers, od mm)
DUCTS        — 11 duct/conduit sizes (id, od, area mm²)
FILL_SINGLE  = 53  (% area limit, single cable in duct)
FILL_MULTIPLE= 40  (% area limit, multiple cables)
SNAP_DIST    = 45  (metres — snap route endpoint to nearby element)
GPON_MIN_RX  = -28 (dBm — GPON power threshold)
FIBER_ATTEN  = 0.35 (dB/km — G.652D)
```

---

## Important Functions

| Function | Location | Does |
|----------|----------|------|
| `placeElem(type,ll,label,fiber,notes)` | ~line 870 | Place infrastructure marker |
| `commitRoute(label,fc,grp,notes,opts)` | ~line 990 | Finalise drawn route + popup + label |
| `finishDraw()` | ~line 975 | End route drawing, show modal |
| `dropGPSPin(ll)` | ~line 1840 | GPS field tool pin drop + auto-chain |
| `findPath(fromId,toId)` | ~line 1290 | BFS graph traversal for loss budget |
| `switchTile(key)` | ~line 1145 | Change map tile layer |
| `updateUI()` | ~line 1720 | Re-render all info panel tabs |
| `generateOTDRTrace(span)` | ftth-planner.jsx | OTDR waveform generator (separate file) |

---

## Known Issues / TODO

- [ ] Electron: native save dialog works but load dialog not yet wired to map restoration
- [ ] GPS accuracy indicator on map (blue accuracy circle) could be more prominent
- [ ] No undo/redo — delete is the only way to remove elements
- [ ] Route snap only works for endpoints; mid-route waypoints don't snap
- [ ] DWDM channel assignment is note-based (manual); should be a route property
- [ ] No multi-user / shared project support yet
- [ ] KML export uses placeholder Google Maps icons; custom SVG icons would be better
- [ ] The OTDR module (generateOTDRTrace) lives in a separate ftth-planner.jsx artifact

## Ideas for Next Features

- Real-time collaboration via WebSockets (share project URL)
- Import existing GeoJSON / KML to start from existing data
- Auto-route snap to roads using OSM Routing API (OSRM)
- Splice loss rollup per route with auto-detected path
- OTDR trace upload / parse (.sor file format)
- Cost estimate PDF report generation
- Network topology export to NetBox / OSP tools
- Offline tile pre-download for selected area (download current viewport tiles at zoom 15–18)

---

## Running the Project

```bash
# Web dev (no build needed)
npm run dev         # → http://localhost:3000

# Desktop dev
npm run dev:electron

# Mobile (requires Android Studio / Xcode)
npm run cap:sync && npm run cap:open:android

# Docker
npm run docker:build && npm run docker:run
# → http://localhost:8080
```

---

## Architecture Notes for Claude Code

1. **Do not add a build system** unless the user asks. The app intentionally works as a single HTML file — this is a feature, not a limitation.
2. **All new features go into `index.html`** unless explicitly moving to a module system.
3. **Leaflet markers use `L.divIcon` with inline HTML** — all styling is inline in the divIcon HTML strings.
4. **The info panel tabs** are controlled by `showTab(name)` — add new tabs there.
5. **Network graph** is built on-the-fly by `buildGraph()` from route `fromEl`/`toEl` properties (set by snap detection).
6. **Capacitor bridge** in the init section detects `window.Capacitor` and overrides GPS + file APIs automatically.
7. **Electron IPC** uses `contextBridge` — renderer calls `window.electronAPI.saveFile()`, main handles `ipcMain.handle('save-file')`.
