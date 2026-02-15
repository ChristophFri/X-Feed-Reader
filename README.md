# X Feed Reader

A local Python tool that scrapes your X.com feed, stores it in SQLite, summarizes it with an LLM, and delivers the result as HTML or via Telegram.

## Quick Start

```bash
git clone https://github.com/user/XfeedReader.git
cd XfeedReader
pip install -e .
playwright install chromium
```

Then just run:

```bash
xfeed
```

On first run, a `config.yaml` is created automatically. If no session is found, a browser window opens for you to log in. After that, the full pipeline runs: scrape, summarize, and open the result in your browser.

## Usage

### Auto-Pilot (default)

```bash
xfeed              # Full pipeline: scrape -> summarize -> open in browser
xfeed --no-open    # Same, but don't open the browser at the end
xfeed --verbose    # Show detailed logging
```

### Scheduled Mode

```bash
xfeed --every 6h          # Run every 6 hours with system tray icon
xfeed --every 30m          # Run every 30 minutes
xfeed --every 1d --no-open # Daily, no browser pop-up
```

When `pystray` is installed, a system tray icon appears with "Run Now" and "Quit" options. Otherwise it falls back to console mode (`Ctrl+C` to stop).

Install tray support:

```bash
pip install -e ".[scheduler]"
```

### Individual Commands

For more control, use subcommands directly:

```bash
xfeed login                        # Open browser for manual login
xfeed scrape                       # Scrape feed (default: 100 tweets)
xfeed scrape --max-tweets 50       # Limit tweets
xfeed scrape --headed              # Visible browser window
xfeed summary                      # Summarize stored tweets
xfeed summary --format html        # HTML output (default)
xfeed summary --format md          # Markdown output
xfeed summary --hours 48           # Last 48 hours
xfeed summary --llm                # Use Claude API
xfeed summary --local-llm          # Use LM Studio
xfeed summary --telegram           # Send to Telegram
xfeed run                          # Scrape + summarize in one step
xfeed run --local-llm --telegram   # With LLM + Telegram
xfeed stats                        # Database statistics
xfeed mark-read                    # Mark all tweets as read
xfeed mark-read --before 2025-01-15
```

### Config Commands

```bash
xfeed config show   # Show current configuration
xfeed config init   # Create template config.yaml
xfeed config path   # Print config file path
```

## Configuration

Edit `config.yaml` in your project directory:

```yaml
browser_profile: "data/browser-profile"
db_path: "data/x_feed.db"
output_dir: "output"
verbose: false

telegram:
  bot_token: ""   # From @BotFather, or set TELEGRAM_BOT_TOKEN env var
  chat_id: ""     # Your chat ID, or set TELEGRAM_CHAT_ID env var

summary:
  hours: 24
  format: "html"              # html or md
  method: "simple"            # simple, llm, or local-llm
  lmstudio_url: "http://localhost:1234"

scrape:
  max_tweets: 100
  headed: false
```

For API keys, create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Summarization Methods

| Method | Description |
|--------|-------------|
| `simple` | Basic keyword extraction, no LLM needed |
| `llm` | Claude API (requires `ANTHROPIC_API_KEY`) |
| `local-llm` | LM Studio running locally (default: `http://localhost:1234`) |

## Project Structure

```
XfeedReader/
├── config.yaml              # Your configuration
├── config.yaml.example      # Template
├── pyproject.toml
├── .env                     # API keys (do not commit)
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point (Typer)
│   ├── scraper.py           # Playwright browser automation
│   ├── database.py          # SQLAlchemy + SQLite
│   ├── summarizer.py        # LLM summarization
│   ├── output.py            # Jinja2 template rendering
│   ├── config.py            # YAML config loading
│   ├── scheduler.py         # Background scheduling + tray icon
│   ├── telegram_notifier.py # Telegram delivery
│   └── utils.py             # Helpers
├── templates/
│   ├── daily_summary.html.j2
│   └── daily_summary.md.j2
├── tests/                   # Unit tests (pytest)
├── data/                    # Database + browser profile
└── output/                  # Generated summaries
```

## License

MIT
