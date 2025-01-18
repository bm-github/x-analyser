# Twitter/X Analyzer

CLI tool for analyzing Twitter/X user activity using OpenRouter API and LLMs.

## Prerequisites

- Python 3.8+
- Twitter/X API Bearer Token
- OpenRouter API Key

## Setup

1. Create a `keys` directory two levels up from the script:
```bash
mkdir -p ../../keys
```

2. Add API keys:
```bash
echo "your-twitter-bearer-token" > ../../keys/x-token.txt
echo "your-openrouter-key" > ../../keys/key-openrouter.txt
```

## Installation

```bash
pip install tweepy requests rich
```

## Usage

Run the analyzer:
```bash
python x-analyser-openrouter.py
```

The tool will:
1. Prompt for a Twitter handle
2. Fetch recent tweets (cached for 24 hours)
3. Allow interactive questions about the user's tweets
4. Generate AI-powered analysis using OpenRouter

## Features

- Tweet caching (24-hour expiry)
- Rich CLI interface
- Interactive Q&A about tweet patterns
- Configurable LLM model selection
- Excludes retweets and replies

## Error Handling

- Validates API keys on startup
- Handles rate limits and API errors
- Provides clear error messages in the CLI

## Dependencies

- `tweepy`: Twitter API client
- `requests`: HTTP client
- `rich`: Terminal formatting
- `pathlib`: File operations

## License

MIT
