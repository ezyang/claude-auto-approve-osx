#!/usr/bin/env python3
import logging
import time
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
import Quartz
from ApplicationServices import AXUIElementCreateApplication, AXUIElementCopyAttributeValue
import HIServices

logger = logging.getLogger(__name__)

def get_frontmost_pid():
    """Get the process ID of the frontmost application.

    Returns:
        int: Process ID of the frontmost application, or None if not found.
    """
    ws = NSWorkspace.sharedWorkspace()
    frontmost_app = ws.frontmostApplication()
    if frontmost_app:
        return frontmost_app.processIdentifier()
    return None

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
                logger.error("Failed to access application's windows - check Accessibility permissions")
                logger.error("Please grant Terminal (or your Python app) Accessibility access in:")
                logger.error("System Preferences > Security & Privacy > Privacy > Accessibility")
            return app_element
        else:
            logger.warning(f"Failed to create accessibility element for '{app_name}'")
            return None
    except Exception as e:
        logger.error(f"Error getting application by name: {e}")
        return None

def click_button_in_dialog(app_name, dialog_title, button_title):
    """Find and click a button in a dialog of the specified application.
    
    Args:
        app_name (str): Name of the application.
        dialog_title (str): Title of the dialog to search for.
        button_title (str): Title of the button to click.
        
    Returns:
        bool: True if the button was found and clicked, False otherwise.
    """
    # Get the application's accessibility element
    app_element = get_application_by_name(app_name)
    if not app_element:
        logger.warning(f"Application '{app_name}' not found")
        return False
    
    # Get the application's windows
    windows = get_ax_window_list(app_element)
    if not windows:
        logger.warning(f"No windows found for application '{app_name}'")
        return False
        
    # Look for the dialog in all windows
    for window in windows:
        # If dialog_title is None, skip title checking
        if dialog_title:
            dialog = find_dialog_with_title(window, dialog_title)
            if dialog:
                button = find_button_with_title(dialog, button_title)
                if button:
                    return perform_press_action(button)
        else:
            # If no specific dialog title, search for the button directly in the window
            button = find_button_with_title(window, button_title)
            if button:
                return perform_press_action(button)
                
    return False

def get_element_attributes(element):
    """Get all attributes of an accessibility element for debugging.
    
    Args:
        element: The accessibility element.
        
    Returns:
        dict: Dictionary of attribute names and values.
    """
    if element is None:
        return {}
        
    error, attr_names = Quartz.AXUIElementCopyAttributeNames(element, None)
    if error:
        return {}
        
    result = {}
    for attr in attr_names:
        error, value = AXUIElementCopyAttributeValue(element, attr, None)
        if not error:
            # Convert complex objects to strings for easier logging
            if hasattr(value, 'description'):
                result[attr] = value.description()
            else:
                result[attr] = str(value)
    
    return result

def dump_application_hierarchy(app_name, max_depth=3):
    """Dump the accessibility hierarchy of an application for debugging.
    
    Args:
        app_name (str): Name of the application.
        max_depth (int): Maximum depth to traverse in the hierarchy.
        
    Returns:
        str: A string representation of the accessibility hierarchy.
    """
    app_element = get_application_by_name(app_name)
    if not app_element:
        return f"Application '{app_name}' not found"
        
    output = [f"Accessibility hierarchy for '{app_name}':"]
    
    def traverse(element, depth=0, path=''):
        if depth > max_depth:
            output.append(f"{'  ' * depth}[Max depth reached]")
            return
            
        # Get all attributes and error codes
        error, attr_names = Quartz.AXUIElementCopyAttributeNames(element, None)
        if error:
            output.append(f"{'  ' * depth}[Error getting attribute names: {error}]")
            return
            
        # Get role and title with error codes
        role = "Unknown"
        title = ""
        role_error, role_value = AXUIElementCopyAttributeValue(element, "AXRole", None)
        if role_error:
            role = f"Unknown (error: {role_error})"
        else:
            role = role_value
            
        title_error, title_value = AXUIElementCopyAttributeValue(element, "AXTitle", None)
        if title_error:
            title = f"[Error: {title_error}]"
        else:
            title = title_value or ""
            
        # Get all attributes with error codes
        all_attrs = {}
        for attr in attr_names:
            err, value = AXUIElementCopyAttributeValue(element, attr, None)
            if err:
                all_attrs[attr] = f"[Error: {err}]"
            else:
                # Convert complex objects to strings for easier logging
                if hasattr(value, 'description'):
                    all_attrs[attr] = value.description()
                else:
                    all_attrs[attr] = str(value)
        
        # Format the current element
        element_str = f"{'  ' * depth}{role}"
        if title:
            element_str += f" ('{title}')"
            
        output.append(element_str)
        
        # Add interesting attributes
        for attr, value in all_attrs.items():
            if attr not in ["AXRole", "AXTitle", "AXChildren"] and not attr.startswith("AX"):
                output.append(f"{'  ' * (depth+1)}{attr}: {value}")
        
        # Traverse children
        children_error, children = AXUIElementCopyAttributeValue(element, "AXChildren", None)
        if children_error:
            output.append(f"{'  ' * (depth+1)}[Error getting children: {children_error}]")
            return
            
        if children:
            for i, child in enumerate(children):
                traverse(child, depth + 1, f"{path}.{i}")
                
    # Start traversal with windows
    windows = get_ax_window_list(app_element)
    if not windows:
        output.append("No windows found or error getting windows")
        
        # Try to get raw window info
        error, attr_names = Quartz.AXUIElementCopyAttributeNames(app_element, None)
        if error:
            output.append(f"Error getting app attributes: {error}")
        else:
            output.append("Application attributes:")
            for attr in attr_names:
                err, value = AXUIElementCopyAttributeValue(app_element, attr, None)
                if err:
                    output.append(f"  {attr}: [Error: {err}]")
                else:
                    output.append(f"  {attr}: {value}")
    else:
        for i, window in enumerate(windows):
            window_title = "Untitled Window"
            title_error, title_value = AXUIElementCopyAttributeValue(window, "AXTitle", None)
            if not title_error and title_value:
                window_title = title_value
                
            output.append(f"\nWindow {i+1}: '{window_title}'")
            traverse(window, 0, f"{i}")
            
    return "\n".join(output)

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
        logger.info(f"Searching window {window_index+1}/{len(windows)}")
        
        window_title = get_ax_attribute_value(window, "AXTitle") or "Untitled Window"
        logger.info(f"Window title: '{window_title}'")
        
        # First try to find a dialog that might be the tool confirmation dialog
        for dialog_role in ["AXSheet", "AXDialog", "AXGroup"]:
            logger.info(f"Looking for dialog role: {dialog_role}")
            dialogs = find_all_elements_with_role(window, dialog_role)
            logger.info(f"Found {len(dialogs)} elements with role {dialog_role}")
            
            all_discovered_dialogs.extend([(dialog_role, get_ax_attribute_value(d, "AXTitle") or "Untitled") for d in dialogs])
            
            for dialog_index, dialog in enumerate(dialogs):
                dialog_title = get_ax_attribute_value(dialog, "AXTitle") or "Untitled Dialog"
                logger.info(f"Checking dialog {dialog_index+1}/{len(dialogs)} with title: '{dialog_title}'")
                
                # First try to find the exact button
                logger.info("Looking for 'Allow for This Chat' button...")
                button = find_button_with_title(dialog, "Allow for This Chat")
                if button:
                    logger.info("✓ Found 'Allow for This Chat' button in dialog")
                    return button
                
                # If not found, look for any button with "Allow" in its title
                logger.info("Looking for any button with 'Allow' in title...")
                all_buttons = find_all_elements_with_role(dialog, "AXButton")
                logger.info(f"Found {len(all_buttons)} buttons in dialog")
                
                for btn in all_buttons:
                    title = get_ax_attribute_value(btn, "AXTitle")
                    all_discovered_buttons.append(title)
                    if title and title == "Allow for This Chat":
                        logger.info(f"✓ Found exact 'Allow for This Chat' button in dialog")
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
                        logger.info("✓ Found dialog mentioning 'codemcp'")
                        codemcp_found = True
                        all_buttons = find_all_elements_with_role(dialog, "AXButton")
                        logger.info(f"Looking through {len(all_buttons)} buttons for approval button")
                        # Return the first button that isn't "Don't Allow"
                        for btn in all_buttons:
                            title = get_ax_attribute_value(btn, "AXTitle")
                            all_discovered_buttons.append(title)
                            if title == "Allow for This Chat":
                                logger.info(f"✓ Found approval button with title: '{title}'")
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
                logger.info(f"✓ Found exact 'Allow for This Chat' button directly in window")
                return btn
    
    # Log all discovered buttons for debugging
    logger.info("No allow button found after full search")
    if all_discovered_buttons:
        unique_buttons = set([str(btn) for btn in all_discovered_buttons if btn])
        logger.info(f"All button titles found: {', '.join(unique_buttons)}")
    else:
        logger.info("No buttons found in any window")
        
    if all_discovered_dialogs:
        unique_dialogs = set([f"{role}:'{title}'" for role, title in all_discovered_dialogs])
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

def get_element_position(element):
    """Get the position of an accessibility element.
    
    Args:
        element: The accessibility element.
        
    Returns:
        tuple: (x, y, width, height) or None if position can't be determined.
    """
    position = get_ax_attribute_value(element, "AXPosition")
    size = get_ax_attribute_value(element, "AXSize")
    
    if position and size:
        try:
            x = position.x()
            y = position.y()
            width = size.width()
            height = size.height()
            return (x, y, width, height)
        except Exception as e:
            logger.debug(f"Error getting element position: {e}")
            return None
    return None

def check_for_codemcp_dialog():
    """Specifically look for the dialog that might contain 'codemcp' text.
    
    This intensive debug function:
    1. Finds the Claude application
    2. Examines all windows and their elements
    3. Checks all text elements for 'codemcp' text
    4. Identifies all nearby buttons
    
    Returns:
        dict: Debug information about the search
    """
    result = {
        "found_codemcp_text": False,
        "all_buttons": [],
        "all_text": [],
        "all_windows": []
    }
    
    app_element = get_application_by_name("Claude")
    if not app_element:
        logger.warning("Claude application not found")
        return result
        
    # Get the application's windows
    windows = get_ax_window_list(app_element)
    if not windows:
        logger.warning("No windows found for Claude application")
        return result
    
    logger.info(f"Found {len(windows)} windows in Claude application")
    
    # Look at all windows
    for window_index, window in enumerate(windows):
        window_title = get_ax_attribute_value(window, "AXTitle") or "Untitled Window"
        window_role = get_ax_attribute_value(window, "AXRole") or "Unknown Role"
        window_info = {
            "index": window_index,
            "title": window_title,
            "role": window_role
        }
        result["all_windows"].append(window_info)
        
        # Get all text elements in this window
        all_text_elements = find_all_elements_with_role(window, "AXStaticText")
        logger.info(f"Window {window_index+1}: '{window_title}' has {len(all_text_elements)} text elements")
        
        # Check all text elements
        for text_index, text_element in enumerate(all_text_elements):
            text_value = get_ax_attribute_value(text_element, "AXValue")
            
            if not text_value:
                text_value = ""
                
            text_info = {
                "window_index": window_index,
                "text_index": text_index,
                "value": text_value[:100] + ("..." if len(text_value) > 100 else "")
            }
            result["all_text"].append(text_info)
            
            # Check for "codemcp" in the text
            if "codemcp" in text_value.lower():
                result["found_codemcp_text"] = True
                logger.info(f"Found text with 'codemcp' in window {window_index+1}")
                logger.info(f"Text content: {text_value[:200]}...")
                
                # Find parent dialog/group
                # (We would need helper functions to traverse up the accessibility hierarchy)
                
                # Find all buttons in this window
                all_buttons_in_window = find_all_elements_with_role(window, "AXButton")
                logger.info(f"Found {len(all_buttons_in_window)} buttons in this window")
                
                for btn_index, btn in enumerate(all_buttons_in_window):
                    btn_title = get_ax_attribute_value(btn, "AXTitle") or ""
                    enabled = get_ax_attribute_value(btn, "AXEnabled")
                    position = get_element_position(btn)
                    
                    btn_info = {
                        "window_index": window_index,
                        "button_index": btn_index,
                        "title": btn_title,
                        "enabled": enabled,
                        "position": position
                    }
                    result["all_buttons"].append(btn_info)
                    
                    logger.info(f"Button {btn_index+1}: '{btn_title}', Enabled: {enabled}, Position: {position}")
    
    return result
