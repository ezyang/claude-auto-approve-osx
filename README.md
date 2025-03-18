# Claude Auto Approval Tool for macOS

This tool automatically approves selected tool requests in the Claude desktop application on macOS. It uses macOS Accessibility APIs to detect and interact with approval dialogs.

This is an OSX port of @Richard-Weiss's Windows auto-approver https://gist.github.com/Richard-Weiss/1ecfee909d839367001199ad179fad28

## Prerequisites

- macOS
- Python 3.12+
- Claude desktop application installed

## Setup

1. Clone this repository:
```
git clone https://github.com/ezyang/claude-auto-approve-osx
cd claude-auto-approve-osx
```

2. Install the package using pip:
```
pip install .
```

Or with uv:
```
uv pip install .
```

3. You need to grant Accessibility permissions to Terminal (or your Python environment app) in System Preferences > Security & Privacy > Privacy > Accessibility.

## Usage

### Basic Usage

Run the tool:
```
claude-auto-approve-osx
```

The tool will:
1. Monitor for the Claude application window
2. Search for "Allow for This Chat" button using Accessibility APIs
3. If found, automatically click the approval button for any tool use
4. Restore focus to your previously active application

Press Ctrl+C to stop the tool.

### Debugging Options

If you're having trouble getting the tool to detect Claude's window properly, use these debugging options:

Dump the accessibility hierarchy for debugging:
```
claude-auto-approve-osx --dump-accessibility
```

Run in debug mode:
```
claude-auto-approve-osx --debug
```

This will dump the accessibility hierarchy and exit.

You can also specify a specific application name:
```
claude-auto-approve-osx --app-name="Your Claude App Name" --debug
```

If you're specifically debugging issues with tool approval dialogs:
```
claude-auto-approve-osx --check-tool-dialogs
```

Debugging works well with [codemcp](https://github.com/ezyang/codemcp), which is how this port was developed and debugged.

### Command Line Options

- `--debug`: Run in debug mode (dump accessibility hierarchy and exit)
- `--app-name`: Specify the Claude application name to look for
- `--dump-accessibility`: Dump the accessibility hierarchy for debugging
- `--check-tool-dialogs`: Intensively search for any tool approval dialogs and report all findings

## Configuration

The tool is configured to automatically approve the following tools:
- list-allowed-directories
- list-denied-directories
- ls
- Is
- google_search
- read-file
- codemcp

To modify the allowed tools or other settings, edit the `Config` class in the source code.

## Troubleshooting

### Common Issues

- **Script can't find Claude window**: Try setting `--app-name` to the correct value
- **Button not being found**: Use `--dump-accessibility` to inspect the accessibility hierarchy
- **Permission issues**: Make sure to grant accessibility permissions to Terminal (or your Python environment app) in System Preferences > Security & Privacy > Privacy > Accessibility
- **Issues with tool approval dialogs**: Use the `--check-tool-dialogs` option to debug tool approval dialogs

## Window Management

The tool includes smart window focus management:

1. When a tool request is detected, the tool will:
   - Save the currently active application
   - Interact with the approval button using Accessibility APIs
   - Restore the original application to the foreground

This allows the tool to run in the background without disrupting your workflow. You can continue working in other applications while the tool automatically handles Claude approvals.

## Security Considerations

This tool is designed to only automatically approve a whitelist of safe tools. Be careful when modifying the allowed tools list to avoid security risks.

## License

MIT