# Claude Auto Approval Tool for macOS

This tool automatically approves selected tool requests in the Claude desktop application on macOS. It uses macOS Accessibility APIs to detect and interact with approval dialogs, with a fallback to computer vision and OCR if needed.

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
2. Search for "Allow for This Chat" button using Accessibility APIs
3. If found, automatically click the approval button
4. Restore focus to your previously active application

Press Ctrl+C to stop the script.

### Method Options

By default, the tool uses macOS Accessibility APIs, which are more reliable and work even when windows are partially occluded. If you prefer the original screenshot-based approach:

```
python claude_auto_approve.py --use-screenshot
```

### Debugging Options

If you're having trouble getting the script to detect Claude's window properly, use these debugging options:

List all visible windows on your screen:
```
python claude_auto_approve.py --list-windows
```

Dump the accessibility hierarchy for debugging:
```
python claude_auto_approve.py --dump-accessibility
```

Run in debug mode:
```
python claude_auto_approve.py --debug
```

This will:
1. If using accessibility mode (default): Dump the accessibility hierarchy
2. If using screenshot mode: Capture a screenshot and generate an HTML report

You can also specify a specific application name:
```
python claude_auto_approve.py --app-name="Your Claude App Name" --debug
```

Debugging works pretty well with [codemcp](https://github.com/ezyang/codemcp),
which is how I made this port and debugged problems with it.

### Command Line Options

- `--debug`: Run in debug mode (dump debug info and exit)
- `--app-name`: Specify the Claude application name to look for
- `--list-windows`: List all visible windows on screen and exit
- `--use-screenshot`: Use the screenshot-based approach instead of accessibility APIs
- `--dump-accessibility`: Dump the accessibility hierarchy for debugging
- `--confidence`: Set the button template matching confidence threshold (0.0-1.0) - only for screenshot mode
- `--dialog-confidence`: Set the dialog template matching confidence threshold (0.0-1.0) - only for screenshot mode

## Configuration

Edit the `Config` class in `claude_auto_approve.py` to customize:
- Allowed tools list
- Detection confidence thresholds
- Polling intervals
- Path to template images
- Claude application name

## Troubleshooting

### Accessibility API Mode (Default)

- **Script can't find Claude window**: Use `--list-windows` to see all visible windows and try setting `--app-name` to the correct value
- **Button not being found**: Use `--dump-accessibility` to inspect the accessibility hierarchy and understand the structure
- **Permission issues**: Make sure to grant accessibility permissions to Terminal (or your Python environment app) in System Preferences > Security & Privacy > Privacy > Accessibility
- **Incorrect button presses**: The tool is designed to identify and press only "Allow"-type buttons, but if you experience issues, you can switch to screenshot mode with `--use-screenshot`

### Screenshot Mode

- **Script can't find Claude window**: Use `--list-windows` to see all visible windows and try setting `--app-name` to the correct value
- **Script captures wrong/small window**: Create a debug report (`--debug`) to see which window is being captured
- **OCR not working**: Verify Tesseract is installed correctly
- **Button not being clicked**: You may need to update the template images to match your current Claude UI version
- **Occluded/overlapped windows**: Make sure Claude is not covered by other windows. Due to macOS security limitations, the script can only capture what's visible on screen in this mode.

## Window Management

The tool includes smart window focus management:

1. When a tool request is detected, the tool will:
   - Save the currently active application
   - If necessary, bring Claude to the foreground (depending on the mode)
   - Click or press the approval button
   - Restore the original application to the foreground

This allows the tool to run in the background without disrupting your workflow. You can continue working in other applications while the tool automatically handles Claude approvals.

The accessibility mode is generally less intrusive as it often doesn't need to bring Claude to the foreground to interact with buttons.

## Security Considerations

This tool is designed to only automatically approve a whitelist of safe tools. Be careful when modifying the allowed tools list to avoid security risks.

## License

MIT
