# Claude Auto Approval Tool for macOS

This tool automatically approves selected tool requests in the Claude desktop application on macOS. It uses computer vision and OCR to detect and interact with approval dialogs.

This is an OSX port of @Richard-Weiss's Windows auto-approver https://gist.github.com/Richard-Weiss/1ecfee909d839367001199ad179fad28

## Prerequisites

- macOS
- Python 3.8+
- Claude desktop application installed
- Tesseract OCR

## Setup

1. Clone this repository:
```
git clone https://github.com/ezyang/claude-auto-approve-osx
cd claude-auto-approve-osx
```

2. Install Tesseract OCR using Homebrew:
```
brew install tesseract
```

3. Run
```
uv run claude-auto-approve-osx
```

## Usage

### Basic Usage

Run the script:
```
python claude_auto_approve.py
```

The script will:
1. Monitor for the Claude application window
2. Search for dialog templates when the window is found
3. Use OCR to check if the tool request matches the allowed list
4. If allowed, automatically click the approval button

Press Ctrl+C to stop the script.

### Debugging Options

If you're having trouble getting the script to detect Claude's window properly, use these debugging options:

List all visible windows on your screen:
```
python claude_auto_approve.py --list-windows
```

Run in debug mode with a specific application name:
```
python claude_auto_approve.py --app-name="Your Claude App Name" --debug
```

This will:
1. Capture a single screenshot of the detected Claude window
2. Save all templates and screenshots to a debug directory
3. Generate an HTML report with all images for easy comparison
4. Open the report in your browser

Debugging works pretty well with [codemcp](https://github.com/ezyang/codemcp),
which is how I made this port and debugged problems with it.

### Command Line Options

- `--debug`: Run in debug mode (capture a single screenshot and exit)
- `--app-name`: Specify the Claude application name to look for
- `--list-windows`: List all visible windows on screen and exit
- `--confidence`: Set the button template matching confidence threshold (0.0-1.0)
- `--dialog-confidence`: Set the dialog template matching confidence threshold (0.0-1.0)

## Configuration

Edit the `Config` class in `claude_auto_approve.py` to customize:
- Allowed tools list
- Detection confidence thresholds
- Polling intervals
- Path to template images
- Claude application name

## Troubleshooting

- **Script can't find Claude window**: Use `--list-windows` to see all windows and try setting `--app-name` to the correct value
- **Script captures wrong/small window**: Create a debug report (`--debug`) to see which window is being captured
- **OCR not working**: Verify Tesseract is installed correctly
- **Button not being clicked**: You may need to update the template images to match your current Claude UI version
- **Occluded/overlapped windows**: Make sure Claude is not covered by other windows. Due to macOS security limitations, the script can only capture what's visible on screen. The script attempts to bring Claude to the foreground, but it's best to keep it unobstructed.

## Window Management

The tool includes smart window focus management:

1. When a tool request is detected, the tool will:
   - Save the currently active application 
   - Bring Claude to the foreground
   - Click the approval button
   - Restore the original application to the foreground

This allows the tool to run in the background without disrupting your workflow. You can continue working in other applications while the tool automatically handles Claude approvals.

## Security Considerations

This tool is designed to only automatically approve a whitelist of safe tools. Be careful when modifying the allowed tools list to avoid security risks.

## License

MIT
