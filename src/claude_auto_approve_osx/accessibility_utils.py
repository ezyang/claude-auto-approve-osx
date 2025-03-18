#!/usr/bin/env python3
import logging
import time
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
import Quartz
from ApplicationServices import AXUIElementCreateApplication, AXUIElementCopyAttributeValue

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
        if title is None or (title_value and title.lower() in title_value.lower()):
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
        
    error = Quartz.AXUIElementPerformAction(element, "AXPress")
    return error == 0

def get_application_by_name(app_name):
    """Get an application's accessibility element by name.
    
    Args:
        app_name (str): Name of the application.
        
    Returns:
        The application's accessibility element, or None if not found.
    """
    app_info = find_app_by_name(app_name)
    if not app_info:
        return None
    return create_ax_ui_element_from_pid(app_info["pid"])

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
            
        attrs = get_element_attributes(element)
        role = attrs.get('AXRole', 'Unknown')
        title = attrs.get('AXTitle', '')
        subrole = attrs.get('AXSubrole', '')
        
        # Format the current element
        element_str = f"{'  ' * depth}{role}"
        if title:
            element_str += f" ('{title}')"
        if subrole:
            element_str += f" [Subrole: {subrole}]"
            
        output.append(element_str)
        
        # Traverse children
        children = get_ax_attribute_value(element, "AXChildren")
        if children:
            for i, child in enumerate(children):
                traverse(child, depth + 1, f"{path}.{i}")
                
    # Start traversal with windows
    windows = get_ax_window_list(app_element)
    if not windows:
        output.append("No windows found")
    else:
        for i, window in enumerate(windows):
            window_title = get_ax_attribute_value(window, "AXTitle") or "Untitled Window"
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
    
    # Look for dialog containing "Allow for This Chat" button
    for window in windows:
        # First try to find a dialog that might be the tool confirmation dialog
        for dialog_role in ["AXSheet", "AXDialog", "AXGroup"]:
            dialogs = find_all_elements_with_role(window, dialog_role)
            for dialog in dialogs:
                # First try to find the exact button
                button = find_button_with_title(dialog, "Allow for This Chat")
                if button:
                    logger.info("Found 'Allow for This Chat' button in dialog")
                    return button
                
                # If not found, look for any button with "Allow" in its title
                all_buttons = find_all_elements_with_role(dialog, "AXButton")
                for btn in all_buttons:
                    title = get_ax_attribute_value(btn, "AXTitle")
                    if title and "Allow" in title:
                        logger.info(f"Found allow button with title: '{title}'")
                        return btn
                        
                # Check if there's text mentioning "codemcp" in the dialog
                static_texts = find_all_elements_with_role(dialog, "AXStaticText")
                for text_element in static_texts:
                    text_value = get_ax_attribute_value(text_element, "AXValue")
                    if text_value and "codemcp" in text_value.lower():
                        # If we found a dialog about codemcp, look harder for any button
                        logger.info("Found dialog mentioning 'codemcp'")
                        all_buttons = find_all_elements_with_role(dialog, "AXButton")
                        # Return the first button that isn't "Don't Allow"
                        for btn in all_buttons:
                            title = get_ax_attribute_value(btn, "AXTitle")
                            if title and "don't" not in title.lower() and "cancel" not in title.lower():
                                logger.info(f"Found approval button with title: '{title}'")
                                return btn
        
        # If not found in dialogs, also look directly in the window
        button = find_button_with_title(window, "Allow for This Chat")
        if button:
            logger.info("Found 'Allow for This Chat' button directly in window")
            return button
            
        # Also check for any button with "Allow" in its title
        all_buttons = find_all_elements_with_role(window, "AXButton")
        for btn in all_buttons:
            title = get_ax_attribute_value(btn, "AXTitle")
            if title and "Allow" in title and "don't" not in title.lower():
                logger.info(f"Found allow button with title: '{title}' directly in window")
                return btn
            
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
        
        if role_value == role:
            results.append(element)
        
        # Recursively check children
        children = get_ax_attribute_value(element, "AXChildren")
        if children:
            for child in children:
                traverse(child)
                
    traverse(parent)
    return results
