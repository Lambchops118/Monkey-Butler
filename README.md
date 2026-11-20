<div align="center">

<h1>Monkey Butler</h1>

<p><strong>Better Understanding Text-to-Speech Large Language Encoder Routine</strong></p>

<p>
  <img src="docs/assets/butler-portrait.gif" alt="Animated Butler portrait" width="420">
</p>

<p>
  <a href="https://github.com/Lambchops118/Talos/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Lambchops118/Talos/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://www.python.org/downloads/release/python-3120/"><img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
  <a href="#requirements"><img alt="Platform: Windows, Linux, and macOS" src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey"></a>
  <a href="#project-status"><img alt="Status: active development" src="https://img.shields.io/badge/status-active%20development-orange"></a>
</p>

<p align="center">This was not made in 4 days by Claude. This project was started sometime around April 2020. Claude/GPT still gets used because im not a geed. </p>

<h2>Peripheral Systems</h2>

<h3><a href="https://github.com/Lambchops118/Kitchen-Recipe-Screen">Kitchen Recipe Display Screen</a></h3>
<h3><a href="https://github.com/Lambchops118/Pump-Power-Controller">Automatic Houseplant Waterer</a></h3>
<h3><a href="https://github.com/Lambchops118/Discord-Voice-Frontend">Discord Voice Module</a></h3>
<h3><a href="https://github.com/Lambchops118/Jeep-CAN-Bus-Interface">Jeep CAN Bus Interface Module</a></h3>
<h3><a href="https://github.com/Lambchops118/Get-A-God-Damn-Job-Al.">"Get A God Damn Job, Al."</a></h3>
<h3><a href="https://github.com/Lambchops118/Soil-Moisture-Sensor-Module">Houseplant Soil Moisture Sensor</a></h3>

</div>

BUTLER is an entirely locally hosted, real-time, voice interaction based artifical intelligence designed to run the house and assist with various projects. It combines a locally hosted language model, locally hosted speech recognition model, memory and awareness system, and IoT node subsytems to create a dynamic, interactable AI system. 


## What It Does

<p align="center">
  <img src="docs/assets/promo.gif" alt="Butler promo">
</p>

- Interacts with the user through a distributed microphone/speaker system in the house, or via text, discord, phone, and console. Can place and recieve phone calls on behalf of the user.
- Stores memories based on interactions, world state, and device interactions. Uses a smaller LLM to compartmentalize memories, find relations, and create new concepts in its memory and awareness database
- Controls plethora of home devices, automotive systems, and software systems and monitors realtime diagnostic data. [Device Information System](docs/DIS.md)
- Stays aware of world context. I.e. stays aware of whether the lights are on or off, what the room temp is like, etc to create a whole picture of the environment it is interacting with. [World Context System](docs/WCS.md)
- Can run durable background jobs or queue up engineering agents on a separate server. (BUTLER does not write code or design circuits directly, this is delegated to an agent running on a dedicated server)
- Exposes diagnostic data through a web based dashboard.

## ===External Hardware Subsystems (IoT Nodes)===
<ins><strong><a href="https://github.com/Lambchops118/Pump-Power-Controller">Houseplant Watering System</a>:</strong></ins> In-house designed and JLCPCB-fabcricated relay control board. Draws power from 12V laptop charger, connects via embedded raspiberry pi pico to MQTT broker. Activates pumps via relay to water a Monstera, Trailing Red, and Philodendron. Water drains from pots back into basin.

<ins><strong><a href="https://github.com/Lambchops118/Soil-Moisture-Sensor-Module">Houseplant Soil Monitoring System</a>:</strong></ins> (Designed, but not fabricated) In-house designed soil moisture sensor. Operates of extremely low power from onboard solar panel. Remains in dormant state for most of operational time, then sends data package to mqtt broker.

<ins><strong><a href="https://github.com/Lambchops118/PoE-5V-Adapter">Room Temperature and Humidity Hysteresis System</a>:</strong></ins> In-House designed room temperature and humidity system that aims to keep the studio apartment at a comfortable temperature and humidity year round. When humidity drops below 40%, it sends a ping to BUTLER to activate the humidifier. When humidity is above 50% it sends a ping to turn it off. Similar for temperature.

<ins>**Smart Lights, Fan, Coffee Pot:**</ins> All lights in the house have been rewired with Tapo/Kasa smart switches. The fan and coffee pot operate off of Kasa smart plugs. BUTLER can freely interact with these.

<ins><strong><a href="https://github.com/Lambchops118/Jeep-CAN-Bus-Interface">Jeep CAN Bus Interface</a>:</strong></ins> (Early Development) Onboard telemetry system for my shitbox Wrangler. Sends CAN bus data back home to BUTLER for preventitive diagnostics.

## ===External Software Subsystems===
<ins><strong><a href="https://github.com/Lambchops118/Kitchen-Recipe-Screen">Kitchen Recipe Screen</a>:</strong></ins> A mounted 1920x1080 monitor in the kitchen with chromium in kiosk mode. This functions as a display method for butler to display recipes as I am cooking in the kitchen.

<ins><strong><a href="https://github.com/Lambchops118/Get-A-God-Damn-Job-Al.">Resume and Application Pipeline ("Get a God Damn Job, Al")</a>:</strong></ins> A fully automated resume creation and job applier. Creates resumes tailored to each listing by pulling from a central pool of information containing my background and projects, then applies using them.

<ins>**Minecraft Server Control:**</ins> Allows BUTLER to turn on the minecraft server, read its data (playercount, etc) and execute commands for management. 

<ins>**Minecraft Player Interface:**</ins> (Fall 26 Grad Research) Allows BUTLER to play minecraft on the server.

<ins><strong><a href="https://github.com/Lambchops118/Discord-Voice-Frontend">Discord Bot</a>:</strong></ins> Discord interface so BUTLER can be in discord and interacted with. Allows BUTLER to join a voice channel and speak with users. Also supports text based communication. All functions are available through discord as normal - communication input is flattened before it reaches the LLM.

## ===Internal Subsystems===
<u>**[World Context System (WCS)](docs/WCS.md):**</u> Handles state data for the environment. This includes things like weather, user location, what is going on in the room, what a user is doing.

<u>**[Device Information System (DIS)](docs/DIS.md):**</u> Handles device state data. This includes things like whether the lights are on or off, whether the watering system is functioning, server status.

<u>**[Long Term Memory System (LTMS)](docs/LTMS.md):**</u> Handles long term memory, correlation, and concepts. Does not handle a long list of device status entries. Includes an LLM to extract and process meaningful information from user interations, DIS, WCS, and other sources. Turns observed patterns and concept in goals. Inlcudes a visual node-graph display to easily view stored memories. 

<u>**[Goal Oriented Executor System (GOES)](docs/GOES.md):**</u> Not Yet Implemented. Takes action based off learned goals from the LTMS.


## Requirements

### Hardware:
- RTX 5080 or greater (mb-core-v1 and faster-whisper model)
- Nvidia a2000 or greater (for LTMS)
- Roomscale microphone and speaker with echo cancellation (for barge-in)

### Software:
- Windows or Ubuntu for deployment, basic development can happen on macOS.
- Python 3.12
- [Ollama](https://ollama.com/) with a configured chat model
- The packages in `requirements/runtime-py312.txt`
- Access to Tailscale, Twilio (optional), Elevenlabs (optional), AWS, and OpenWeather.

## Architecture

The current implementation uses several independently deployable processes:

| Process | Responsibility |
| --- | --- |
| Main service (`python -m butler`) | Router, scheduler, agent runtime, memory, MCP client, text/SMS servers, and display-state projection |
| Room voice worker (`python -m butler.voice.worker`) | Wake word, microphone capture, local STT, TTS playback, and proactive-speech endpoint |
| InfoPanel (`python -m butler.display.worker`) | Independently deployable pygame display client |
| Ollama | Local model server used by the main service |

The main service and room voice worker share `.venv-runtime`, but they are still
separate operating-system processes. The voice worker sends recognized commands
to the main service's HTTP API; the InfoPanel polls that API for display state.
The launcher starts and supervises both processes independently. A separate
public phone bridge is used only when phone calling is configured, and the
optional Discord voice frontend lives in its own repository.

The default inference path is local: Ollama provides an OpenAI-compatible LLM
endpoint and `faster-whisper` handles speech-to-text. The tracked default model
name is `mb-core-v1:latest`; this repository also includes a Ministral 3 14B
profile. Hosted LLM fallback requires an OpenAI API key, and hosted STT fallback
can be disabled when audio must remain local.

For a deeper technical assessment, see
[Architecture Review](docs/ARCHITECTURE_REVIEW.md). Awareness design and status
live in [Awareness and Memory](docs/awareness-memory/README.md).


## Quick start

### 1. Create the environments

The main service and room voice worker share the runtime environment:

```bash
python3.12 -m venv .venv-runtime
source .venv-runtime/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements/runtime-py312.txt
```

The separately deployable display uses a focused environment:

```bash
python3.12 -m venv .venv-display
.venv-display/bin/python -m pip install -r requirements/display-py312.txt
```

On Windows, use the interpreters under `Scripts` instead of `bin`; for example:

```powershell
py -3.12 -m venv .venv-runtime
.venv-runtime\Scripts\python.exe -m pip install -r requirements/runtime-py312.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
```

`settings.env` contains committed, non-secret defaults. Put API keys, tokens,
and passwords only in `.env`. Real environment variables override both files.

The default local LLM settings point to Ollama:

```env
BUTLER_LLM_BACKEND=ollama
BUTLER_LLM_BASE_URL=http://127.0.0.1:11434/v1
BUTLER_LLM_MODEL=mb-core-v1:latest
BUTLER_LOCAL_STT=1
BUTLER_VOICE_STREAMING=1
```

Local LLM and STT operation do not require an OpenAI key. The committed
`models/mb-core-v1.Modelfile` references an owner-machine Ollama blob, so it is
not a portable recipe from a public base model.
`models/ministral-butler.Modelfile` is the reproducible profile included in the
repository.

### 3. Start the stack

Launch the supervised Windows control panel:

```powershell
.\Start-Butler.ps1
```

The launcher manages Ollama, the main service, room voice worker, display,
component selection, GPU assignment, and logs. Docker/PostgreSQL is no longer
required for Butler startup. For a console-only launch with the last saved component selection:

```powershell
.\Start-Butler.ps1 --no-gui
```

## Running components separately

```bash
# Main service: agent runtime, scheduler, text/SMS APIs, and display state
.venv-runtime/bin/python -m butler

# Room voice worker; connects to the main service over HTTP
.venv-runtime/bin/python -m butler.voice.worker

# Display client (after installing display requirements)
.venv-display/bin/python -m butler.display.worker

# Debug dashboard
.venv-runtime/bin/python -m butler.debug_dashboard
```

The former awareness subsystem is archived in
[`archive/awareness`](archive/awareness/README.md). Its automatic household context,
state/history tools, alerts, reminders, briefings, and registered pump/fan actions
are retired pending separately scoped replacements. Existing databases, local
conversation history, and hardware firmware have not been deleted or migrated.

## Application database

Conversation history/saved facts, background jobs and phone records share
`db/butler.sqlite3`, configured by `BUTLER_DB_PATH`. Memory clearing affects conversation tables only.
See [database ownership and migration guide](docs/DATABASE.md).

## Interfaces

### Text chat

The main service exposes a small HTTP API and browser UI, intended for localhost
or a private Tailscale network. Set `TEXT_AGENT_API_TOKEN` in `.env` before
exposing it beyond loopback.

```bash
python -m butler.text.client \
  --url "http://<tailscale-hostname-or-ip>:8420" \
  --token "<your-token>" \
  --session-id "main-pc"
```

Windows users can run the same client through
`scripts\clients\butler-chat.cmd`.

### Debug dashboard

Run `python -m butler.debug_dashboard`, then open
`http://127.0.0.1:8787`. The dashboard shows interaction flow, component health, pipeline latency, prompt composition, model placement, memory usage, jobs, tool reliability, and available system telemetry. It is read-only and binds to loopback by default because it can expose private data.

### Phone and SMS

<<<<<<< HEAD
#### Inbound calls 
The Twilio number's voice webhook points at Talos, which admits only allowlisted callers whose carrier attests the number (SHAKEN/STIR `TN-Validation-Passed-A`) and rejects everything else. Admitted calls go to the ElevenLabs agent through its register-call API, with a briefing from Talos memory. During the call, the agent uses server tools (`recall`, `house_status`, `ask_talos`), and the transcript goes back into Talos memory afterwards. The local listener (`butler/phone/inbound_server.py`, default `127.0.0.1:8431`) is published with Tailscale Funnel at `/phone` and is disabled by default. Setup, agent prompt, and tool definitions:
[`docs/phone-inbound/SETUP.md`](docs/phone-inbound/SETUP.md).

### SMS and Phone Control
Phone calls use ElevenLabs for the conversational voice agent and Twilio for
PSTN transport. SMS commands enter the same agent path as local text chat. The tracked settings enable both integrations, but they become operational only when their required credentials, identifiers, URLs, and allowlists are present. The public phone bridge and SMS webhook should be the only internet-facing components; keep the main Butler runtime private.
>>>>>>> 1ef7b7c0f3f810da998e5b778ff6d855dffcaaa8

Relevant variables are documented in `.env.example` and `settings.env`.

## Tools and integrations
Set `BUTLER_MCP_SERVERS` to configure the full server list. Tool names must be unique; use `tool_prefix` when servers could collide. Detailed guides:
- [Tool Implementation Guide](docs/TOOL_IMPLEMENTATION_GUIDE.md)
- [Filesystem MCP](docs/filesystem-mcp.md)
- [Minecraft Diagnostics](docs/minecraft-forge-diagnostics.md)


## Repository layout

```text
butler/                     Main application and service packages
archive/awareness/          Retired source, migrations, deployment and tests
InfoPanel/                  Pygame display modules and visual assets
Peripherals/                MicroPython firmware and MQTT helpers
docker/                     Container and test-broker configuration
docs/                       Architecture, operations, and subsystem guides
models/                     Ollama model definitions
prototypes/                 Legacy and experimental UI/visualization work
requirements/               Dependency manifests for each runtime
scripts/                    Secondary command-line wrappers
tests/                      Unit and integration tests
tools/                      Maintenance, diagnostics, and asset exporters
```

Some persistent identifiers still use `talos` because they are external or
on-disk compatibility contracts, including database names, MQTT topics, state
files, and the GitHub repository URL. New source code, configuration, and
display names use Butler.

## Development

The CI workflow currently verifies that Python files compile under Python 3.12:

```bash
python -m compileall butler InfoPanel Peripherals tests
```

Run focused tests for the area you change, for example:

```bash
.venv-runtime/bin/python -m unittest tests/test_request_classifier.py
```

The project includes hardware, audio, database, and network integrations, so
the full test suite may require services or devices not available on every
development machine.

## Project status

Butler is under active development. Releases are created manually; the
repository does not currently publish installers or binary artifacts. See the
[implementation status](docs/awareness-memory/IMPLEMENTATION_STATUS.md) for the
archived awareness subsystem's historical work; it is no longer active.

This repository does not currently include an open-source license. Unless a
license is added, the source is visible but no reuse rights are granted.
