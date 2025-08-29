# GrowCastle Auto Bot

Usage:
1. Clone repo
1. Navigate to project root
1. Run `python growcastle.py` (or `python growcastle.py --no-upgrades` if you don't want the bot to buy upgrades automatically)

## Colony mode

1. Open the colony window
1. Select the world you want to automatically colonize
1. Go to the bottom right of the world
	- If you are doing infinite colony, this isn't needed. Instead, click the colony once to select it for the bot.
1. Run `python growcastle.py --colony`.

## Live dashboard (TUI)

A live terminal dashboard is available to monitor and orchestrate multiple instances (like htop). It renders a table of instances with live state updates.

Prerequisites:
- Python 3.11+
- ADB accessible for each device/instance
- Install dependencies: `pip install -r requirements.txt`

Start from instances file (default: instances.json in repo root):

```
python dashboard.py --instances instances.json
```

Or fallback to explicit devices (without instances file):

```
python dashboard.py --devices 127.0.0.1:5555 127.0.0.1:5556 127.0.0.1:5557 --config config.json
```

Forward extra args to each instance after `--` (applies to CLI devices mode):

```
python dashboard.py --devices 127.0.0.1:5555 127.0.0.1:5556 -- --no-upgrades --captcha-retry-attempts 5
```

Notes:
- The dashboard relies on `growcastle.py` emitting machine-readable status lines when launched with `--status` (handled automatically by dashboard).
- Each instance prints regular logs as well; the dashboard only reads status lines (`__STATUS__ {json}`).

### Instances config file

You can configure device ports and display names in a JSON file:

1. Copy `instances.example.json` to `instances.json` and edit it.
2. Run the dashboard with (or rely on default):

```
python dashboard.py --instances instances.json
```

Schema:

```
{
	"python": ".venv/Scripts/python.exe",          # Optional: override Python executable
	"script": "growcastle.py",                    # Optional: override script path
	"instances": [
		{ "name": "acc-01", "device": "127.0.0.1:5555", "config": "config.json", "extra_args": ["--no-upgrades"] },
		{ "name": "acc-02", "device": "127.0.0.1:5556", "config": "config.json" }
	]
}
```

Fields:
- instances[].device: required (ADB serial/host:port)
- instances[].name: optional display name
- instances[].config: optional per-instance config.json
- instances[].extra_args: optional extra args array passed to `growcastle.py`
