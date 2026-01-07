# Azure Speech Pronunciation Assessment POC

A minimal proof-of-concept for assessing pronunciation using Azure Cognitive Services Speech SDK.

## Features

- Records audio from the default microphone
- Assesses pronunciation against a reference text: "I would like a cup of coffee."
- Provides word-level granularity analysis
- Displays accuracy, fluency, completeness, and pronunciation scores
- Identifies problem words based on error types and accuracy thresholds

## Prerequisites

- Python 3.7 or higher
- Azure Speech Service subscription (get your key and region from [Azure Portal](https://portal.azure.com))
- Microphone access

## Installation

### Windows (PowerShell)

```powershell
# Create virtual environment
py -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install azure-cognitiveservices-speech python-dotenv
```

### macOS / Linux

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install azure-cognitiveservices-speech python-dotenv
```

## Configuration

1. Copy `.env.example` to `.env`:
   ```powershell
   # Windows
   copy .env.example .env
   
   # macOS / Linux
   cp .env.example .env
   ```

2. Edit `.env` and add your Azure Speech credentials:
   ```
   AZURE_SPEECH_KEY=your_key_here
   AZURE_SPEECH_REGION=your_region_here
   ```

## Usage

### Basic usage (default settings)

```bash
python main.py
```

### With custom threshold

```bash
python main.py --threshold 70
```

### With custom language/locale

```bash
python main.py --lang en-GB
```

### Combined options

```bash
python main.py --threshold 75 --lang en-US
```

## Command-line Arguments

- `--threshold` (default: 80.0): Word accuracy threshold (0-100). Words below this threshold are flagged as problems.
- `--lang` (default: en-US): Locale for speech recognition (e.g., `en-US`, `en-GB`, `es-ES`).

## Output

The script displays:

1. **Summary scores:**
   - Recognized text
   - Accuracy score
   - Fluency score
   - Completeness score
   - Pronunciation score

2. **Problem words:** Words where:
   - `error_type != "None"`, OR
   - `accuracy_score < threshold`

Each problem word shows its error type and accuracy score (if applicable).

## Error Handling

The script handles common errors:

- **NoMatch**: Speech could not be recognized (check microphone input)
- **Canceled**: Request was canceled (displays reason and error details)
- **Missing credentials**: Missing `AZURE_SPEECH_KEY` or `AZURE_SPEECH_REGION` in `.env`

## Exit Codes

- `0`: Success
- `1`: Recognition error (NoMatch, Canceled, or unexpected result)
- `2`: Configuration error (missing credentials)

## Notes

- The script uses word-level granularity with `EnableMiscue=True` for detailed analysis
- The reference text is hardcoded as: "I would like a cup of coffee."
- Accuracy scores are not meaningful for "Omission" errors and are displayed as "—" in those cases
