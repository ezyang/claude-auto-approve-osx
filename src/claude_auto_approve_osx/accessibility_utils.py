#!/usr/bin/env python3
import logging
import time
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
import Quartz
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
)
import HIServices

logger = logging.getLogger(__name__)


def get_running_applications():
    """Get a list of all running applications.

    Returns:
        list: List of dictionaries containing application info.
    """
    apps = NSWorkspace.sharedWorkspace().runningApplications()
    return [
        {
            "name": app.localizedName(),
            "bundle_id": app.bundleIdentifier(),
            "pid": app.processIdentifier(),
        }
        for app in apps
    ]


def find_app_by_name(app_name):
    """Find an application by name.

    Args:
        app_name (str): Name of the application to find.

    Returns:
        dict: Dictionary with application info, or None if not found.
    """
    apps = get_running_applications()

    # Try exact match first
    for app in apps:
        if app["name"] == app_name:
            return app

    # Try case-insensitive match
    for app in apps:
        if app_name.lower() in app["name"].lower():
            return app

    return None


def create_ax_ui_element_from_pid(pid):
    """Create an accessibility UI element from a process ID.

    Args:
        pid (int): Process ID of the application.

    Returns:
        AXUIElement: Accessibility UI element for the application.
    """
    if pid is None:
        return None
    return AXUIElementCreateApplication(pid)


def get_ax_attribute_value(element, attribute):
    """Get the value of an accessibility attribute.

    Args:
        element: The accessibility element.
        attribute (str): The attribute to retrieve.

    Returns:
        The attribute value, or None if the attribute doesn't exist.
    """
    if element is None:
        return None

    error, value = AXUIElementCopyAttributeValue(element, attribute, None)

    if error:
        logger.debug(f"Error getting attribute '{attribute}': {error}")
        return None
    return value


def get_ax_window_list(app_element):
    """Get a list of all windows belonging to an application.

    Args:
        app_element: The application's accessibility element.

    Returns:
        list: A list of window elements, or an empty list if none found.
    """
    windows = get_ax_attribute_value(app_element, "AXWindows")
    return windows or []


def find_element_with_role_and_title(parent, role, title=None):
    """Find an accessibility element with the specified role and title.

    Args:
        parent: The parent accessibility element to search within.
        role (str): The accessibility role to search for (e.g., "AXButton").
        title (str, optional): The title to match, if any.

    Returns:
        The matching accessibility element, or None if not found.
    """
    if parent is None:
        return None

    role_value = get_ax_attribute_value(parent, "AXRole")
    title_value = get_ax_attribute_value(parent, "AXTitle")

    # If this element matches the criteria, return it
    if role_value == role:
        if title is None or (title_value and (title_value == title)):
            return parent

    # Recursively check children
    children = get_ax_attribute_value(parent, "AXChildren")
    if children:
        for child in children:
            result = find_element_with_role_and_title(child, role, title)
            if result:
                return result

    return None


def find_button_with_title(parent, title):
    """Find a button with the specified title.

    Args:
        parent: The parent accessibility element to search within.
        title (str): The button title to search for.

    Returns:
        The button element, or None if not found.
    """
    return find_element_with_role_and_title(parent, "AXButton", title)


def find_dialog_with_title(parent, title):
    """Find a dialog with the specified title.

    Args:
        parent: The parent accessibility element to search within.
        title (str): The dialog title to search for.

    Returns:
        The dialog element, or None if not found.
    """
    return find_element_with_role_and_title(parent, "AXSheet", title)


def perform_press_action(element):
    """Press an accessibility element (e.g., button).

    Args:
        element: The accessibility element to press.

    Returns:
        bool: True if successful, False otherwise.
    """
    if element is None:
        return False

    # Perform the button press
    HIServices.AXUIElementPerformAction(element, "AXPress")
    return True


def get_application_by_name(app_name):
    """Get an application's accessibility element by name.

    Args:
        app_name (str): Name of the application.

    Returns:
        The application's accessibility element, or None if not found.
    """
    app_info = find_app_by_name(app_name)
    if not app_info:
        logger.warning(f"Application '{app_name}' not found in running applications")
        return None

    logger.info(f"Found application '{app_name}' with PID {app_info['pid']}")

    try:
        app_element = create_ax_ui_element_from_pid(app_info["pid"])
        if app_element:
            # Check if we can actually access the element - will fail if accessibility permissions are missing
            windows = get_ax_attribute_value(app_element, "AXWindows")
            if windows is None:
                logger.error(
                    "Failed to access application's windows - check Accessibility permissions"
                )
                logger.error(
                    "Please grant Terminal (or your Python app) Accessibility access in:"
                )
                logger.error(
                    "System Preferences > Security & Privacy > Privacy > Accessibility"
                )
            return app_element
        else:
            logger.warning(f"Failed to create accessibility element for '{app_name}'")
            return None
    except Exception as e:
        logger.error(f"Error getting application by name: {e}")
        return None


def find_allow_button_in_claude():
    """Find the 'Allow for This Chat' button in the Claude application.

    This function looks for:
    1. The specific 'Allow for This Chat' button
    2. Any button with "Allow" in its title if the specific button isn't found

    Returns:
        The button element if found, None otherwise.
    """
    app_element = get_application_by_name("Claude")
    if not app_element:
        logger.warning("Claude application not found")
        return None

    # Get the application's windows
    windows = get_ax_window_list(app_element)
    if not windows:
        logger.warning("No windows found for Claude application")
        return None

    logger.info(f"Found {len(windows)} windows in Claude application")

    # Collect all discovered buttons for logging
    all_discovered_buttons = []
    all_discovered_dialogs = []

    # Look for dialog containing "Allow for This Chat" button
    for window_index, window in enumerate(windows):
        logger.info(f"Searching window {window_index + 1}/{len(windows)}")

        window_title = get_ax_attribute_value(window, "AXTitle") or "Untitled Window"
        logger.info(f"Window title: '{window_title}'")

        # First try to find a dialog that might be the tool confirmation dialog
        for dialog_role in ["AXSheet", "AXDialog", "AXGroup"]:
            logger.debug(f"Looking for dialog role: {dialog_role}")
            dialogs = find_all_elements_with_role(window, dialog_role)
            logger.debug(f"Found {len(dialogs)} elements with role {dialog_role}")

            all_discovered_dialogs.extend(
                [
                    (dialog_role, get_ax_attribute_value(d, "AXTitle") or "Untitled")
                    for d in dialogs
                ]
            )

            for dialog_index, dialog in enumerate(dialogs):
                dialog_title = (
                    get_ax_attribute_value(dialog, "AXTitle") or "Untitled Dialog"
                )
                logger.debug(
                    f"Checking dialog {dialog_index + 1}/{len(dialogs)} with title: '{dialog_title}'"
                )

                # First try to find the exact button
                logger.debug("Looking for 'Allow for This Chat' button...")
                button = find_button_with_title(dialog, "Allow for This Chat")
                if button:
                    logger.info("✓ Found 'Allow for This Chat' button in dialog")
                    return button

                # If not found, look for any button with "Allow" in its title
                logger.debug("Looking for any button with 'Allow' in title...")
                all_buttons = find_all_elements_with_role(dialog, "AXButton")
                logger.debug(f"Found {len(all_buttons)} buttons in dialog")

                for btn in all_buttons:
                    title = get_ax_attribute_value(btn, "AXTitle")
                    all_discovered_buttons.append(title)
                    if title and title == "Allow for This Chat":
                        logger.info(
                            f"✓ Found exact 'Allow for This Chat' button in dialog"
                        )
                        return btn

                # Check if there's text mentioning "codemcp" in the dialog
                logger.debug("Looking for text mentioning 'codemcp'...")
                static_texts = find_all_elements_with_role(dialog, "AXStaticText")
                logger.debug(f"Found {len(static_texts)} text elements")

                codemcp_found = False
                for text_element in static_texts:
                    text_value = get_ax_attribute_value(text_element, "AXValue")
                    if text_value:
                        logger.debug(f"Text content: {text_value[:100]}...")
                    if text_value and "codemcp" in text_value.lower():
                        # If we found a dialog about codemcp, look harder for any button
                        codemcp_found = True
                        all_buttons = find_all_elements_with_role(dialog, "AXButton")
                        # Return the first button that isn't "Don't Allow"
                        for btn in all_buttons:
                            title = get_ax_attribute_value(btn, "AXTitle")
                            all_discovered_buttons.append(title)
                            if title == "Allow for This Chat":
                                logger.info(
                                    f"✓ Found approval button with title: '{title}'"
                                )
                                return btn

                if not codemcp_found:
                    logger.debug("No text mentioning 'codemcp' found in this dialog")

        # If not found in dialogs, also look directly in the window
        logger.info("Looking for 'Allow for This Chat' button directly in window...")
        button = find_button_with_title(window, "Allow for This Chat")
        if button:
            logger.info("✓ Found 'Allow for This Chat' button directly in window")
            return button

        # Also check for any button with "Allow" in its title
        logger.info("Looking for any Allow button directly in window...")
        all_buttons = find_all_elements_with_role(window, "AXButton")
        logger.info(f"Found {len(all_buttons)} buttons in window")

        for btn in all_buttons:
            title = get_ax_attribute_value(btn, "AXTitle")
            all_discovered_buttons.append(title)
            if title and title == "Allow for This Chat":
                logger.info(
                    f"✓ Found exact 'Allow for This Chat' button directly in window"
                )
                return btn

    # Log all discovered buttons for debugging
    logger.info("No allow button found after full search")
    if all_discovered_buttons:
        unique_buttons = set([str(btn) for btn in all_discovered_buttons if btn])
        logger.info(f"All button titles found: {', '.join(unique_buttons)}")
    else:
        logger.info("No buttons found in any window")

    if all_discovered_dialogs:
        unique_dialogs = set(
            [f"{role}:'{title}'" for role, title in all_discovered_dialogs]
        )
        logger.info(f"All dialog types found: {', '.join(unique_dialogs)}")
    else:
        logger.info("No dialogs/groups found in any window")

    return None


def find_all_elements_with_role(parent, role):
    """Find all accessibility elements with a specific role.

    Args:
        parent: The parent accessibility element to search within.
        role (str): The accessibility role to search for.

    Returns:
        list: List of matching elements.
    """
    results = []

    def traverse(element):
        if element is None:
            return

        role_value = get_ax_attribute_value(element, "AXRole")
        title_value = get_ax_attribute_value(element, "AXTitle") or ""

        if role_value == role:
            results.append(element)

        # Recursively check children
        children = get_ax_attribute_value(element, "AXChildren")
        if children:
            for child in children:
                traverse(child)

    traverse(parent)
    return results
