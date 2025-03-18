#!/usr/bin/env python3
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Tuple, Optional, Self, Dict, Any

from claude_auto_approve_osx.accessibility_utils import (
    find_allow_button_in_claude,
    perform_press_action,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AccessibilityAutoApprover:
    """Automatically approves tool requests in the Claude desktop app using macOS Accessibility APIs."""

    def auto_approve(self) -> Tuple[bool, Optional[str]]:
        """Find and click the 'Allow for This Chat' button using accessibility APIs.

        This method:
        1. Searches for the 'Allow for This Chat' button in any window/dialog
        2. Presses the button if found

        Returns:
            Tuple[bool, Optional[str]]:
                - First value: Whether a button was found and clicked.
                - Second value: Reason code for failures or None on success.
                  Possible values: "no_window", "button_not_found", "error"
        """
        try:
            # Find the 'Allow for This Chat' button
            button = find_allow_button_in_claude()

            if not button:
                logger.debug("Allow button not found via accessibility")
                return False, "button_not_found"

            # Press the button
            logger.info("Found and pressing 'Allow' button")
            success = perform_press_action(button)

            return not success, None

        except Exception as e:
            logger.error(f"Error in auto_approve (accessibility): {e}", exc_info=True)
            return False, "error"

    def run(self):
        """Main execution loop with dynamic delay between checks.

        Continuously monitors for approval buttons with adaptive delay times
        based on detection results. Runs until interrupted by user with Ctrl+C.
        """
        logger.info("Starting accessibility-based auto-approval script for Claude")

        print("Press Ctrl+C to stop the script")

        try:
            while True:
                result, reason = self.auto_approve()

                current_delay = 1.0
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
            "This tool automatically detects when a tool request appears in Claude and "
            "clicks the approval button, allowing you to continue working without "
            "having to manually approve each request."
        ),
    )
    args = parser.parse_args()

    # Use accessibility-based auto-approver
    logger.info("Using accessibility-based auto-approver")
    auto_approver = AccessibilityAutoApprover()
    auto_approver.run()


if __name__ == "__main__":
    main()
