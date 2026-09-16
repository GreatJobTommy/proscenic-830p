# Proscenic 830P — local Home Assistant + sticky occupancy map

Local (LAN) control and a persistent occupancy map for the **Proscenic 830P** robot vacuum. The official ProscenicHome map flood-fills rooms and forgets bumper hits once the robot later squeezes under furniture. This project keeps those obstacles.

Firmware on the unit this was built for: **Main 1.0.3**, **MCU 1.4.3**.

This 830P on the LAN:

| Field | Value |
| --- | --- |
| Device ID | `bf4d77d05964608b34enbm` |
| UUID | `936b5c32ba35da61` |
| SN | `SSAM17UYE023DC` |
| MAC | `68:57:2d:87:87:e9` |
| LAN IP | `192.168.178.63` (Tuya 3.3 / TCP 6668) |
| Product key | `ofqlgafdltzahwlh` |

The “Wi-Fi IP” shown in ProscenicHome is often the **WAN** address, not the LAN address. Use the Fritz/DHCP IPv4 (here `.63`).

## 830P vs 790T protocol

The 830P is an **8xx Tuya** robot. Local control is **Tuya protocol 3.3 on TCP port 6668** (same family as the 820T / 850T). `@gibranZawahra` confirmed the 830 on [edenhaus/ha-prosenic](https://github.com/edenhaus/ha-prosenic).

The older **790T** stack ([deblockt/hass-proscenic-790T-vacuum](https://github.com/deblockt/hass-proscenic-790T-vacuum), [felix-engelmann/robotbona](https://github.com/felix-engelmann/robotbona)) talks **robotbona on ports 8888 / 10684**. This repo does **not** assume robotbona. A probe tries 6668 first and only then 8888/10684. If your unit answers robotbona instead of Tuya, switch adapters after that probe — occupancy still applies.

## What the 830P actually has

| Item | Value |
| --- | --- |
| Body | 330 mm diameter, 76 mm height |
| Climb | 10 mm conservative / 15 mm advertised — this code uses 10 mm |
| Radio | **2.4 GHz Wi-Fi only** (no 5 GHz) |
| Navigation | Gyroscope (IPNAS 3.0). No LiDAR. No on-device no-go zones. |
| Modes | smart, wall-follow (`wallfollow`), single-room (`single`), spot (`sprial` — firmware spelling), mop |
| Fan | `ECO` / `normal` / `strong` |
| Faults | bumper/collision, off-ground/cliff, trapped, dustbin, left/right wheel, side/roller brush, water tank |
| Mop | 350 ml tank; mop replaces the dustbin |

Spot clean is encoded as **`sprial`** (the 8xx firmware string confirmed on the 830), not `spiral`.

## Occupancy mapping

Scan/probe mode consumes a **pose + bumper** stream (and an optional decoded track) and writes a grid:

- **UNKNOWN** — default. Never flood-filled into floor.
- **FREE** — only cells whose centre sat under the 330 mm body disk.
- **OCCUPIED** — bumper (or cliff) contact at the body radius along heading. **Never demotes to free**, even if the body later drives through the same XY (under a sofa, through a chair gap, etc.).

A later squeeze-under or squeeze-past therefore leaves the obstacle in the map. The official app’s “it’s one open room” behaviour is exactly what this merge rule forbids.

Onboard auto-clean **still uses the robot’s own gyro planner**. This software cannot flash Main 1.0.3 / MCU 1.4.3. The better map is for Home Assistant, visualisation, and an optional remote-control overlay (`DP 26` forward/left/right/stop). It will not stop the built-in auto-clean from bumping.

Gyro odometry drifts. Treat the grid as a bumper-informed occupancy sketch, not a LiDAR map.

## Local credentials (`device_id` / `local_key`)

Tuya LAN needs three values: **host IP**, **device_id**, **local_key**.

1. Put the 830P on the same **2.4 GHz** LAN (the robot will not join 5 GHz).
2. Pair once with ProscenicHome / Tuya so a `local_key` exists.
3. Read `device_id` + `local_key` with [tinytuya wizard](https://github.com/jasonacox/tinytuya) or by intercepting the Tuya/Proscenic cloud login (same process as ha-prosenic).
4. Point Home Assistant at the robot’s DHCP IP. `nmap -p 6668 --open` on your subnet finds Tuya 8xx units.
5. After that, **block the robot’s WAN** if you want. Runtime control is local.

Tuya LAN typically allows **one socket client**. Home Assistant and ProscenicHome will fight if both hold the connection. Leave the phone app closed while HA is connected.

Alexa can stay paired through the cloud; this integration does not replace Alexa certification and does not need it.

## Home Assistant

The 830P talks **Tuya LAN only** at runtime (no ProscenicHome app). Clone the whole repo so the library and the custom component stay together:

```bash
# Home Assistant OS / Supervised (SSH / Samba add-on)
git clone https://github.com/GreatJobTommy/proscenic-830p.git /config/proscenic-830p
mkdir -p /config/custom_components
ln -s /config/proscenic-830p/custom_components/proscenic_830p /config/custom_components/proscenic_830p
```

Home Assistant Core / Container: `pip install git+https://github.com/GreatJobTommy/proscenic-830p.git` and copy or symlink `custom_components/proscenic_830p` into `<config>/custom_components/`. Restart HA.

**Preferred:** Settings → Devices → Add integration → **Proscenic 830P**. Choose *ProscenicHome login* (same email/password as the app). The flow fetches `local_key` once and then talks LAN only; the password is not stored.

ProscenicHome may list this unit as **D600** in the inbox while device info and the name **schlurp** are the 830P. The matcher accepts that listing (and Tuya sweeper category `sd`); it still prefers the known LAN id `bf4d77d05964608b34enbm` when present.

YAML still works if you already have the key:

```yaml
# configuration.yaml
vacuum:
  - platform: proscenic_830p
    host: 192.168.178.63
    device_id: bf4d77d05964608b34enbm
    local_key: YOUR_LOCAL_KEY
    name: Saugroboter
```

| HA action | Tuya DP |
| --- | --- |
| start | `25=smart` |
| pause | re-issue last mode on `25` (no dedicated pause DP on 8xx) |
| stop | `26=stop` |
| dock | `25=chargego` |
| wall-follow | `25=wallfollow` |
| single-room | `25=single` |
| spot | `25=sprial` |
| mop | `25=mop` |
| fan | `27=ECO\|normal\|strong` |
| battery / state / faults | `39` / `38` / `11` |

Extra services: `wall_follow`, `single_room`, `mop`, `remote_control`.

## Kartierung pass

A dedicated mapping mode starts at the dock, drives a pose+bumper stream, and builds a **25 mm** occupancy grid (a 100 mm wooden post spans multiple cells on both axes). Occupied bumper hits stay occupied; unknown cells are never flood-filled into floor. After the first hit the drive policy backs off and **re-approaches from a second heading** (circumnavigate) instead of only turning left.

```bash
python -m proscenic_830p.launch_kartierung tests/fixtures/kartierung_post.json
```

Output lists `DOCK_CELL` (charging station / start pose) and `OCCUPIED_CELL` (sticky obstacles). Two runs of the same fixture are identical.

## Live map, coverage, and edge (Kanten)

Watch the occupancy grid grow one pose+bumper sample at a time, then drive **only where the 330 mm body already fit** (free cells). A separate **Kanten** pass walks the occupied frontier with the body on free cells and a **front-left or front-right side brush** (55° on the 330 mm disk) against the edge — map geometry, not the Tuya `wallfollow` DP.

```bash
python -m proscenic_830p.launch_live tests/fixtures/kartierung_post.json
```

Output: growing `SNAPSHOT k known=…` lines, then `COVERAGE_POSE` and `EDGE_POSE`. Two runs match. Unknown cells stay unknown; onboard auto-clean still does not follow this map.

## Occupancy CLI

```bash
python -m proscenic_830p.launch_map tests/fixtures/occupancy_trace.json
```

Prints every `OCCUPIED_CELL`, free/unknown counts, and an ASCII grid (`#` occupied, `.` free, `?` unknown). Re-running the same fixture is deterministic.

Live scan/probe on the robot (no pose DP on Tuya 6668) dead-reckons from `DP 26` and treats fault bit 64 (bumper) / 32 (cliff) as contacts:

```python
from proscenic_830p.probe import probe_tick
new_pose, command = probe_tick(grid, pose, status, dt_s=0.2)
adapter.send_dps(command)  # {"26": "forward"} or {"26": "turnleft"}
```

Python API for a recorded trace:

```python
from proscenic_830p.occupancy import PoseSample, scan_probe

grid = scan_probe([
    PoseSample(x_mm=900, y_mm=500, heading_deg=0, bumper=True),
    PoseSample(x_mm=1100, y_mm=500, heading_deg=0, bumper=False),  # squeeze-under
])
assert grid.cell_at(1065, 500).name == "OCCUPIED"
```

## Development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Limits (read this)

- No firmware replace, no LiDAR retrofit, no on-device no-go zones.
- Auto-clean pathing cannot be rewritten from HA; overlay + map only.
- Official cloud map is not the source of truth.
- 790T is not first-class; probe may detect it, occupancy is shared, wire protocol is not.
- Climb specs disagree (10 mm vs 15 mm); commands and helpers use 10 mm.

## License

MIT. Prior art: edenhaus/ha-prosenic (Tuya DPs, 830 confirmed), MrVidipy/ha-proscenic, 790T occupancy ideas from deblockt / robotbona (unknown / floor / wall + track — used here as the occupancy model, not the 830P wire protocol).
