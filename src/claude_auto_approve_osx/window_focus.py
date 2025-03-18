#!/usr/bin/env python3
import logging
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps

logger = logging.getLogger(__name__)


def get_frontmost_app():
    """Get the currently frontmost application.

    Returns:
        dict: Information about the frontmost app including name and bundle ID.
    """
    ws = NSWorkspace.sharedWorkspace()
    frontmost_app = ws.frontmostApplication()
    if frontmost_app:
        return {
            "name": frontmost_app.localizedName(),
            "bundle_id": frontmost_app.bundleIdentifier(),
            "app_instance": frontmost_app,
        }
    return None


def activate_app_by_name(app_name: str) -> bool:
    """Activate (bring to foreground) an application by name.

    Args:
        app_name: Name of the application to activate.

    Returns:
        bool: True if application was found and activated, False otherwise.
    """
    apps = NSWorkspace.sharedWorkspace().runningApplications()

    # Try exact match first
    for app in apps:
        if app.localizedName() == app_name:
            logger.info(f"Focusing {app_name} application")
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True

    # If exact match fails, try case-insensitive match or contains
    for app in apps:
        if app_name.lower() in app.localizedName().lower():
            logger.info(
                f"Focusing app with name containing '{app_name}': {app.localizedName()}"
            )
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True

    return False


def activate_app_by_bundle_id(bundle_id: str) -> bool:
    """Activate (bring to foreground) an application by bundle ID.

    Args:
        bundle_id: Bundle ID of the application to activate.

    Returns:
        bool: True if application was found and activated, False otherwise.
    """
    apps = NSWorkspace.sharedWorkspace().runningApplications()

    for app in apps:
        if app.bundleIdentifier() == bundle_id:
            logger.info(f"Focusing application with bundle ID {bundle_id}")
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True

    return False
