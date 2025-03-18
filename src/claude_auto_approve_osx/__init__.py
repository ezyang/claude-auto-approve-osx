#!/usr/bin/env python3
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Tuple, Optional, Self, Dict, Any

from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps

from claude_auto_approve_osx.window_focus import (
    get_frontmost_app,
    activate_app_by_name,
    activate_app_by_bundle_id,
)
from claude_auto_approve_osx.accessibility_utils import (
    get_application_by_name,
    find_allow_button_in_claude,
    perform_press_action,
    dump_application_hierarchy,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Config:
    """Configuration singleton for the Claude auto-approval tool.

    This class implements the Singleton pattern, ensuring only one configuration
    instance exists throughout the application. It stores paths to required image
    templates, application settings, and runtime parameters.

    Attributes:
        _instance: Class variable storing the singleton instance
        script_dir: Path to the directory containing the script
        claude_app_name: App name of Claude application
        claude_window_title: Window title for the Claude application
        allowed_tools: List of approved tool names that can be automatically accepted
        tool_pattern: Regular expression for extracting tool and server names
        normal_delay: Standard delay between approval checks in seconds
        no_window_delay: Delay when Claude window is not found
        no_image_delay: Delay when approval button is not found
        blocked_tool_delay: Delay when a tool is detected but not in allowed list
        debug_mode: Whether to run in debug mode (dump accessibility hierarchy and exit)
        debug_dir: Directory to save debug screenshots and info
    """

    _instance = None

    def __new__(cls):
        """Override the instance creation method to implement the singleton pattern.

        Returns:
            Config: The singleton Config instance.
        """
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize configuration settings with default values.

        Sets up file paths, application settings, and operational parameters.
        """
        self.script_dir = Path(__file__).parent

        self.claude_app_name = "Claude"
        self.claude_window_title = "Claude"

        self.allowed_tools = [
            "list-allowed-directories",
            "list-denied-directories",
            "ls",
            "Is",
            "google_search",
            "read-file",
            "codemep",
            "codemcp",
        ]
        self.tool_pattern = re.compile(r"Run\s+(\S+)\s+from\s+(\S+)")

        self.normal_delay = 0.5
        self.no_window_delay = 10.0
        self.no_image_delay = 1.0
        self.blocked_tool_delay = 3.0

        # Debug mode settings
        self.debug_mode = False
        self.debug_dir = self.script_dir / "debug"


class AccessibilityAutoApprover:
    """Automatically approves tool requests in the Claude desktop app using macOS Accessibility APIs.

    This class detects and processes approval requests from the Claude application by using
    the macOS Accessibility APIs to find and interact with UI elements directly, rather than
    using image recognition. This provides a more reliable way to detect and click buttons
    regardless of visual appearance or window occlusion.

    Attributes:
        config: Configuration singleton with settings.
        previous_foreground_app: Stores information about the previously focused app.
    """

    def __init__(self) -> None:
        """Initialize AccessibilityAutoApprover with required services and configuration."""
        self.config = Config()
        self.previous_foreground_app = None

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if the requested tool is in the allowed list.

        Args:
            tool_name: Name of the tool being requested.

        Returns:
            bool: True if the tool is allowed, False otherwise.
        """
        return tool_name in self.config.allowed_tools

    def auto_approve(self) -> Tuple[bool, Optional[str]]:
        """Find and click the 'Allow for This Chat' button using accessibility APIs.

        This method:
        1. Finds the Claude application
        2. Searches for the 'Allow for This Chat' button in any window/dialog
        3. Presses the button if found

        Returns:
            Tuple[bool, Optional[str]]:
                - First value: Whether a button was found and clicked.
                - Second value: Reason code for failures or None on success.
                  Possible values: "no_window", "button_not_found", "error"
        """
        try:
            # Save the currently focused app before potentially switching
            self.previous_foreground_app = get_frontmost_app()

            # Find the 'Allow for This Chat' button
            button = find_allow_button_in_claude()

            if not button:
                logger.debug("Allow button not found via accessibility")
                return False, "button_not_found"

            # Press the button
            logger.info("Found and pressing 'Allow' button")
            success = perform_press_action(button)

            # Restore the previously focused app
            if self.previous_foreground_app:
                # Only log at debug level
                app_name = self.previous_foreground_app.get("name", "unknown")
                logger.debug(f"Restoring previous foreground app: {app_name}")
                
                app_instance = self.previous_foreground_app.get("app_instance")
                if app_instance:
                    app_instance.activateWithOptions_(
                        NSApplicationActivateIgnoringOtherApps
                    )
                else:
                    # Fallback using bundle ID if app instance not available
                    bundle_id = self.previous_foreground_app.get("bundle_id")
                    if bundle_id:
                        activate_app_by_bundle_id(bundle_id)
                    else:
                        # Last resort, try by name
                        activate_app_by_name(
                            self.previous_foreground_app.get("name", "")
                        )
                time.sleep(0.1)  # Short delay to ensure app is focused

            return not success, None

        except Exception as e:
            logger.error(f"Error in auto_approve (accessibility): {e}", exc_info=True)
            return False, "error"

    def debug_accessibility(self) -> None:
        """Dump the accessibility hierarchy for debugging purposes.

        This method queries the Claude application's accessibility hierarchy
        and saves it to a text file in the debug directory.
        """
        debug_dir = self.config.debug_dir
        debug_dir.mkdir(exist_ok=True)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        hierarchy = dump_application_hierarchy("Claude")

        # Save the hierarchy to a file
        hierarchy_path = debug_dir / f"accessibility_hierarchy-{timestamp}.txt"
        with open(hierarchy_path, "w") as f:
            f.write(hierarchy)

        logger.info(f"Saved accessibility hierarchy to {hierarchy_path}")

    def run(self):
        """Main execution loop with dynamic delay between checks.

        Continuously monitors for approval buttons with adaptive delay times
        based on detection results. Runs until interrupted by user with Ctrl+C.
        """
        logger.info("Starting accessibility-based auto-approval script for Claude")

        # If debug mode is enabled, just dump the accessibility hierarchy and exit
        if self.config.debug_mode:
            logger.info("Running in debug mode - will dump accessibility hierarchy and exit")
            self.debug_accessibility()
            logger.info("Debug dump complete. Exiting.")
            return

        print("Press Ctrl+C to stop the script")
        current_delay = self.config.normal_delay

        try:
            while True:
                result, reason = self.auto_approve()

                if reason == "no_window":
                    logger.debug("Claude application not found")
                    current_delay = self.config.no_window_delay
                elif reason == "button_not_found":
                    logger.debug("Allow button not found")
                    current_delay = self.config.no_image_delay
                else:
                    current_delay = self.config.normal_delay

                logger.debug(f"Waiting {current_delay} seconds before next check")
                time.sleep(current_delay)

        except KeyboardInterrupt:
            logger.info("Script stopped by user")


def main():
    """Main entry point with command-line argument handling.

    Parses command-line arguments and runs the auto-approval script
    with the specified configuration.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Claude Auto-Approval Tool for macOS",
        epilog=(
            "This tool automatically manages window focus: when a tool request is detected, "
            "it saves the currently active application, brings Claude to the foreground, "
            "clicks the approval button, and restores the original application to foreground. "
            "This allows you to continue working in other applications without disruption."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in debug mode (dump accessibility hierarchy and exit)",
    )
    parser.add_argument(
        "--app-name", type=str, help="Claude application name to look for"
    )
    parser.add_argument(
        "--dump-accessibility",
        action="store_true",
        help="Dump the accessibility hierarchy for debugging",
    )
    parser.add_argument(
        "--check-codemcp-dialog",
        action="store_true",
        help="Intensively search for the codemcp dialog and report all findings",
    )
    args = parser.parse_args()

    # Initialize configuration
    config = Config()

    # Apply command-line overrides
    if args.debug:
        config.debug_mode = True
    if args.app_name is not None:
        config.claude_app_name = args.app_name

    # Special mode to dump accessibility hierarchy
    if args.dump_accessibility:
        approver = AccessibilityAutoApprover()
        approver.debug_accessibility()
        return

    # Special mode to check for codemcp dialog
    if args.check_codemcp_dialog:
        from claude_auto_approve_osx.accessibility_utils import check_for_codemcp_dialog
        logger.info("Running intensive search for codemcp dialog...")
        results = check_for_codemcp_dialog()

        # Create debug output
        debug_dir = Path(__file__).parent / "debug"
        debug_dir.mkdir(exist_ok=True)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = debug_dir / f"codemcp_dialog_search-{timestamp}.txt"

        with open(output_path, "w") as f:
            f.write("=== CODEMCP DIALOG SEARCH RESULTS ===\n\n")
            f.write(f"Found 'codemcp' text: {results['found_codemcp_text']}\n\n")

            f.write("=== WINDOWS ===\n")
            for window in results["all_windows"]:
                f.write(f"Window {window['index']}: '{window['title']}' ({window['role']})\n")

            f.write("\n=== BUTTONS ===\n")
            for btn in results["all_buttons"]:
                f.write(f"Button: '{btn['title']}', Enabled: {btn['enabled']}, Position: {btn['position']}\n")

            f.write("\n=== TEXT ELEMENTS ===\n")
            for text in results["all_text"]:
                if "codemcp" in text["value"].lower():
                    f.write(f"*** TEXT WITH CODEMCP (Window {text['window_index']}) ***\n")
                    f.write(f"{text['value']}\n\n")

        logger.info(f"Detailed debug output saved to {output_path}")
        return

    # Use accessibility-based auto-approver
    logger.info("Using accessibility-based auto-approver")
    auto_approver = AccessibilityAutoApprover()
    auto_approver.run()


if __name__ == "__main__":
    main()
