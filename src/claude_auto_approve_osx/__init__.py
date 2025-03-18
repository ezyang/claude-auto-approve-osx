#!/usr/bin/env python3
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Tuple, Optional, Self, Dict, Any

import mss
import pytesseract
from PIL import Image, ImageEnhance
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
import Quartz
import subprocess
import pyautogui

from claude_auto_approve_osx.window_focus import (
    get_frontmost_app,
    activate_app_by_name,
    activate_app_by_bundle_id,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


class Config:
    """Configuration singleton for the Claude auto-approval tool.

    This class implements the Singleton pattern, ensuring only one configuration
    instance exists throughout the application. It stores paths to required image
    templates, application settings, and runtime parameters.

    Attributes:
        _instance: Class variable storing the singleton instance
        script_dir: Path to the directory containing the script
        button_image: Path to the approval button image template
        dialog_template_paths: List of paths to dialog box template images
        claude_app_name: App name of Claude application
        claude_window_title: Window title for the Claude application
        confidence_threshold: Threshold for image matching confidence (0.0-1.0)
        dialog_confidence: Confidence threshold for dialog box detection
        allowed_tools: List of approved tool names that can be automatically accepted
        tool_pattern: Regular expression for extracting tool and server names
        normal_delay: Standard delay between approval checks in seconds
        no_window_delay: Delay when Claude window is not found
        no_image_delay: Delay when approval button is not found
        blocked_tool_delay: Delay when a tool is detected but not in allowed list
        cache_timeout: Window handle cache timeout in seconds
        debug_mode: Whether to run in debug mode (capture single screenshot and exit)
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
        self.button_image = str(self.script_dir / "approve_button.png")
        self.dialog_template_paths = [
            str(self.script_dir / "dialog_template.png"),
            str(self.script_dir / "dialog_template_expanded.png"),
        ]

        self.claude_app_name = "Claude"
        self.claude_window_title = "Claude"
        self.confidence_threshold = 0.7
        self.dialog_confidence = 0.2

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
        self.cache_timeout = 30

        # Debug mode settings
        self.debug_mode = False
        self.debug_dir = self.script_dir / "debug"


class TemplateManager:
    """Singleton class for managing template images used in the Claude auto-approval process.

    This class ensures only one instance of template images is loaded into memory.
    It manages the approval button and dialog templates needed for image recognition.

    Attributes:
        _instance (TemplateManager): Class variable storing the singleton instance.
        _initialized (bool): Tracks whether the instance has been initialized.
        approve_button_template (Image): The loaded image template for the approval button.
        dialog_templates (List[Image]): The loaded image templates for the dialog boxes.
    """

    _instance = None
    _initialized = False

    def __new__(cls) -> Self:
        """Override the instance creation method to implement singleton pattern.

        Returns:
            TemplateManager: The singleton TemplateManager instance.
        """
        if cls._instance is None:
            cls._instance = super(TemplateManager, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the template manager if not already initialized.

        Checks if the manager has been initialized and if not, sets up the template
        images and loads them from disk.
        """
        if not self._initialized:
            self.approve_button_template = None
            self.dialog_templates = []
            self.__load_templates()
            self._initialized = True

    def __load_templates(self) -> None:
        """Load template images from disk.

        Reads the approve button and dialog template images from the paths defined
        in the configuration and stores them as instance attributes.
        """
        config = Config()
        self.approve_button_template = Image.open(config.button_image)
        self.dialog_templates = [
            Image.open(path) for path in config.dialog_template_paths
        ]
        logger.info(
            f"Template images loaded: 1 button, {len(self.dialog_templates)} dialog variants"
        )


class WindowManager:
    """Singleton class for managing Claude application window interactions on macOS.

    This class handles window discovery, window information retrieval,
    and screenshot capturing. It implements caching to reduce overhead from
    repeated window handle lookups.

    Attributes:
        _instance: Class variable storing the singleton instance.
        cached_window_id: Cached window ID for Claude application.
        cached_window_info: Cached window position and dimensions.
        last_check_time: Timestamp of the last window handle check.
        config: Reference to the application configuration.
    """

    _instance = None

    def __init__(self) -> None:
        """Initialize window manager instance variables.

        Note that actual initialization happens in _initialize() which is
        called from __new__() to ensure proper singleton instantiation.
        """
        self.cached_window_id = None
        self.cached_window_info = None
        self.last_check_time = 0

    def __new__(cls) -> Self:
        """Override instance creation to implement singleton pattern.

        Returns:
            WindowManager: The singleton instance.
        """
        if cls._instance is None:
            cls._instance = super(WindowManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Set up required dependencies and configurations for the window manager.

        Called only once during the first instance creation.
        """
        self.config = Config()

    def get_claude_window_with_cache(
        self,
    ) -> Tuple[Optional[int], Optional[Tuple[int, int, int, int]]]:
        """Get the Claude window handle and information with caching.

        Caches window information for performance and only refreshes when
        the cache timeout has expired or no cached information exists.

        Returns:
            Tuple[Optional[int], Optional[Tuple[int, int, int, int]]]:
                A tuple containing:
                - Window ID or None if not found
                - Tuple of (x, y, width, height) or None if window not found
        """
        current_time = time.time()

        # NOTE: Focusing code is disabled as requested
        # self.focus_claude_app()
        # time.sleep(0.2)  # Short delay to let window manager respond

        if (
            self.cached_window_id is None
            or current_time - self.last_check_time > self.config.cache_timeout
        ):
            self.cached_window_id = self.get_claude_window_id()
            if self.cached_window_id:
                self.cached_window_info = self.get_window_info(self.cached_window_id)
            else:
                self.cached_window_info = None
            self.last_check_time = current_time

        return self.cached_window_id, self.cached_window_info

    def get_claude_window_id(self) -> Optional[int]:
        """Find the Claude window ID by matching app and window title.

        Uses Quartz CoreGraphics functions to enumerate windows and find the Claude application
        by matching application name from config.

        Returns:
            Optional[int]: Window ID if found, None otherwise.
        """
        # Get all windows
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )

        # Print all window information for debugging
        logger.info(f"Found {len(windows)} windows on screen")

        claude_windows = []

        for window in windows:
            app_name = window.get("kCGWindowOwnerName", "")
            window_title = window.get("kCGWindowName", "")
            window_id = window.get("kCGWindowNumber")
            window_bounds = window.get("kCGWindowBounds", {})
            window_layer = window.get("kCGWindowLayer", -1)

            # Convert bounds to string for logging
            bounds_str = (
                f"{window_bounds.get('X', '?')},{window_bounds.get('Y', '?')}"
                f" {window_bounds.get('Width', '?')}x{window_bounds.get('Height', '?')}"
            )

            # Log all windows for debugging
            logger.info(
                f"Window: '{app_name}' - '{window_title}' (ID: {window_id}, Layer: {window_layer}, Bounds: {bounds_str})"
            )

            # Collect all windows that might be Claude
            if (
                app_name.lower() == self.config.claude_app_name.lower()
                or "claude" in app_name.lower()
            ):
                claude_windows.append(
                    {
                        "app_name": app_name,
                        "title": window_title,
                        "id": window_id,
                        "bounds": bounds_str,
                        "layer": window_layer,
                        "raw_bounds": window_bounds,
                    }
                )

        if claude_windows:
            # Sort by layer and size (prefer topmost window and larger windows)
            sorted_windows = sorted(
                claude_windows,
                key=lambda w: (
                    w["layer"],
                    -(
                        w["raw_bounds"].get("Width", 0)
                        * w["raw_bounds"].get("Height", 0)
                    ),
                ),
            )

            logger.info(
                f"Found {len(claude_windows)} Claude windows, selecting: "
                + f"'{sorted_windows[0]['app_name']}' - '{sorted_windows[0]['title']}' "
                + f"(ID: {sorted_windows[0]['id']}, Layer: {sorted_windows[0]['layer']}, "
                + f"Bounds: {sorted_windows[0]['bounds']})"
            )

            return sorted_windows[0]["id"]

        logger.info("No Claude windows found")
        return None

    def get_window_info(self, window_id: int) -> Tuple[int, int, int, int]:
        """Get the position and dimensions of a window.

        Args:
            window_id (int): Window ID to get information for.

        Returns:
            Tuple[int, int, int, int]: Window position and size as (x, y, width, height).
        """
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow, window_id
        )

        if windows and len(windows) == 1:
            window_bounds = windows[0].get("kCGWindowBounds")
            x = window_bounds.get("X", 0)
            y = window_bounds.get("Y", 0)
            width = window_bounds.get("Width", 0)
            height = window_bounds.get("Height", 0)
            logger.info(
                f"Found window with size: {width}x{height} at position: {x},{y}"
            )
            return x, y, width, height

        # Return zeros if window not found
        logger.warning("Window not found or has invalid dimensions")
        return 0, 0, 0, 0

    def capture_window_screenshot(
        self, x: int, y: int, width: int, height: int, window_id: Optional[int] = None
    ) -> Image.Image:
        """Capture a screenshot of a window, even if it's obscured by other windows.

        Args:
            x (int): Left coordinate of the region to capture.
            y (int): Top coordinate of the region to capture.
            width (int): Width of the region to capture.
            height (int): Height of the region to capture.
            window_id (Optional[int]): Window ID to capture. If provided, will attempt to
                                      capture the window even if it's obscured.

        Returns:
            Image.Image: PIL Image object containing the screenshot.
        """
        # If window_id is provided, try to use the macOS-specific window capture method
        # that can capture obscured windows
        if window_id is not None:
            try:
                logger.info(
                    f"Attempting to capture window {window_id} directly using CGWindowListCreateImage"
                )

                # Instead of using the provided x,y coordinates, capture the entire window
                # using CGRectNull which will get the full window bounds automatically
                window_image = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,  # Use null rectangle to get the whole window
                    Quartz.kCGWindowListOptionIncludingWindow,  # Only include the specified window
                    window_id,  # The specific window to capture
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                    | Quartz.kCGWindowImageShouldBeOpaque,
                )

                if window_image:
                    # Convert the CGImage to a PIL Image
                    width = Quartz.CGImageGetWidth(window_image)
                    height = Quartz.CGImageGetHeight(window_image)

                    logger.info(
                        f"Captured window directly using Quartz: {width}x{height}"
                    )

                    # Create a bitmap context and draw the image
                    color_space = Quartz.CGColorSpaceCreateDeviceRGB()
                    context = Quartz.CGBitmapContextCreate(
                        None,
                        width,
                        height,
                        8,  # bits per component
                        width * 4,  # bytes per row (4 bytes per pixel: RGBA)
                        color_space,
                        Quartz.kCGImageAlphaPremultipliedLast,
                    )

                    # Draw the image in the context
                    rect = Quartz.CGRectMake(0, 0, width, height)
                    Quartz.CGContextDrawImage(context, rect, window_image)

                    # Get the image from the context
                    image_ref = Quartz.CGBitmapContextCreateImage(context)

                    # Convert to PIL Image
                    provider = Quartz.CGImageGetDataProvider(image_ref)
                    data = Quartz.CGDataProviderCopyData(provider)
                    buffer = bytes(data)

                    # Create a PIL Image from the raw data - BGRA is how macOS stores it
                    pil_image = Image.frombuffer(
                        "RGBA", (width, height), buffer, "raw", "BGRA", 0, 1
                    )

                    return pil_image
            except Exception as e:
                logger.error(f"Error capturing window using Quartz: {e}")
                logger.warning("Falling back to screen region capture")

        # Fall back to the MSS screen capture method (can't capture obscured windows)
        logger.info(
            f"Using MSS to capture screen region at {x},{y} with size {width}x{height}"
        )
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": width, "height": height}
            screenshot = sct.grab(monitor)
            image = Image.frombytes(
                "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
            )
            return image

    def list_all_windows(self) -> None:
        """List all visible windows on the screen with detailed information.

        This is useful for debugging to find the correct window to target.
        """
        print("\n==== All Visible Windows ====\n")

        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )

        print(f"Found {len(windows)} windows on screen\n")

        # Group windows by application
        apps = {}
        for window in windows:
            app_name = window.get("kCGWindowOwnerName", "Unknown")
            if app_name not in apps:
                apps[app_name] = []
            apps[app_name].append(window)

        # Print window information grouped by app
        for app_name, app_windows in sorted(apps.items()):
            print(f"\n== Application: {app_name} ({len(app_windows)} windows) ==")

            for window in app_windows:
                window_title = window.get("kCGWindowName", "")
                window_id = window.get("kCGWindowNumber")
                window_bounds = window.get("kCGWindowBounds", {})
                window_layer = window.get("kCGWindowLayer", -1)
                window_alpha = window.get("kCGWindowAlpha", 1.0)
                window_memory = window.get("kCGWindowMemoryUsage", 0)

                # Convert bounds to string for logging
                bounds_str = (
                    f"{window_bounds.get('X', '?')},{window_bounds.get('Y', '?')}"
                    f" {window_bounds.get('Width', '?')}x{window_bounds.get('Height', '?')}"
                )

                print(f"  Window: '{window_title}'")
                print(f"    ID: {window_id}")
                print(f"    Layer: {window_layer} (lower = closer to front)")
                print(f"    Bounds: {bounds_str}")
                print(f"    Alpha: {window_alpha}")
                print(f"    Memory: {window_memory}")
                print(f"    Is key window: {window.get('kCGWindowIsOnscreen', False)}")
                print(
                    f"    Backing store type: {window.get('kCGWindowSharingState', 'Unknown')}"
                )
                print("")

        print('\nTIP: Use --app-name="App Name" to target a specific application')
        print("     Use --debug to capture a screenshot of the detected window")
        print("     Here are some potential commands to try:\n")

        # Suggest commands for likely Claude-related windows
        for app_name in apps.keys():
            if "claude" in app_name.lower() or "anthropic" in app_name.lower():
                print(
                    f'     python claude_auto_approve.py --app-name="{app_name}" --debug'
                )

    def focus_claude_app(self):
        """Attempts to focus the Claude application by name.

        This is different from focus_claude_window as it focuses the application
        itself rather than a specific window. This is useful before window detection.

        Returns:
            bool: True if Claude app was found and activated, False otherwise.
        """
        apps = NSWorkspace.sharedWorkspace().runningApplications()

        # Try exact match first
        for app in apps:
            if app.localizedName() == self.config.claude_app_name:
                logger.info(f"Focusing {self.config.claude_app_name} application")
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                return True

        # If exact match fails, try case-insensitive match or contains
        for app in apps:
            if self.config.claude_app_name.lower() in app.localizedName().lower():
                logger.info(
                    f"Focusing app with name containing '{self.config.claude_app_name}': {app.localizedName()}"
                )
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                return True

        # Try with common Claude-related names as fallback
        common_names = ["Claude", "Anthropic", "Claude AI"]
        for name in common_names:
            if name == self.config.claude_app_name:
                continue  # Skip if it's the same as the already tried name

            for app in apps:
                if name.lower() in app.localizedName().lower():
                    logger.info(
                        f"Focusing app with common Claude name '{name}': {app.localizedName()}"
                    )
                    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                    return True

        logger.warning(
            f"Could not find Claude application to focus. Checked for: {self.config.claude_app_name} and common names"
        )
        return False

    def focus_claude_window(self):
        """Brings the Claude application window to the foreground.

        Returns:
            bool: True if Claude was found and activated, False otherwise.
        """
        apps = NSWorkspace.sharedWorkspace().runningApplications()
        for app in apps:
            if app.localizedName() == self.config.claude_app_name:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                logger.info(f"Focused {self.config.claude_app_name} application")
                return True

        logger.warning(
            f"Could not find {self.config.claude_app_name} application to focus"
        )
        return False


class OCRService:
    """Singleton class for providing optical character recognition services.

    This class implements the Singleton pattern to ensure only one OCR service
    instance exists. It handles configuration and text extraction from images
    using Tesseract OCR, specifically focused on identifying tool requests
    in Claude dialogs.

    Attributes:
        _instance: Class variable storing the singleton instance.
        _initialized: Tracks whether the instance has been initialized.
        is_configured: Boolean indicating if Tesseract OCR is properly configured.
        config: Reference to the application configuration.
    """

    _instance = None
    _initialized = False

    def __new__(cls) -> Self:
        """Override the instance creation method to implement singleton pattern.

        Returns:
            OCRService: The singleton OCRService instance.
        """
        if cls._instance is None:
            cls._instance = super(OCRService, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the OCR service if not already initialized."""
        self.is_configured = False
        if not self._initialized:
            self._initialize()
            self.__class__._initialized = True

    def _initialize(self) -> None:
        """Set up required dependencies and configurations for the OCR service.

        Called only once during the first instance initialization.
        """
        self.config = Config()
        self.is_configured = False

    def configure_ocr(self) -> bool:
        """Configure and verify Tesseract OCR availability.

        Checks if Tesseract is properly installed and accessible. If already
        configured, returns immediately to avoid redundant checks.

        If the default configuration fails, tries common system locations for macOS.

        Returns:
            bool: True if Tesseract OCR is properly configured, False otherwise.
        """
        if self.is_configured:
            return True

        try:
            pytesseract.get_tesseract_version()
            self.is_configured = True
            logger.info("Tesseract OCR configured successfully")
            return True
        except Exception as e:
            logger.warning(f"Default Tesseract configuration failed: {e}")

        # Common macOS paths for Tesseract
        paths_to_try = [
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
            "/opt/local/bin/tesseract",
        ]

        for path in paths_to_try:
            if os.path.isfile(path):
                try:
                    pytesseract.pytesseract.tesseract_cmd = path
                    pytesseract.get_tesseract_version()
                    self.is_configured = True
                    logger.info(f"Tesseract OCR configured successfully using {path}")
                    return True
                except Exception as e:
                    logger.debug(
                        f"Tesseract configuration failed with path {path}: {e}"
                    )

        # Try using 'which' command to find tesseract
        try:
            result = subprocess.run(
                ["which", "tesseract"], capture_output=True, text=True, check=True
            )
            path = result.stdout.strip()
            if path:
                pytesseract.pytesseract.tesseract_cmd = path
                pytesseract.get_tesseract_version()
                self.is_configured = True
                logger.info(f"Tesseract OCR configured successfully using {path}")
                return True
        except Exception as e:
            logger.debug(f"Failed to find tesseract using 'which': {e}")

        logger.error(
            "Tesseract OCR configuration failed. Please install it with 'brew install tesseract'"
        )
        return False

    def extract_tool_info(
        self, screenshot: Image.Image, roi=None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract tool and server name using Tesseract OCR.

        Processes a screenshot image to extract the tool name and server name
        using OCR. If a region of interest (roi) is provided, only that portion
        of the image will be processed. Large images are automatically resized
        to improve OCR performance.

        Args:
            screenshot: PIL Image object containing the screenshot to analyze.
            roi: Optional bounding box defining a region of interest within the
                screenshot. If provided, only this region is processed.

        Returns:
            Tuple containing:
                - Tool name (str or None if not found)
                - Server name (str or None if not found)
        """
        try:
            if roi:
                x, y, w, h = roi
                x_start = x
                y_start = y
                x_end = min(screenshot.width, x + w)
                y_end = min(screenshot.height, y + h)

                cropped_img = screenshot.crop((x_start, y_start, x_end, y_end))

                if w * h > 1000000:
                    scale = 0.75
                    cropped_img = cropped_img.resize(
                        (
                            int(cropped_img.width * scale),
                            int(cropped_img.height * scale),
                        )
                    )
            else:
                cropped_img = screenshot

            cropped_img = ImageEnhance.Contrast(cropped_img).enhance(1.5)

            text = pytesseract.image_to_string(cropped_img)

            match = self.config.tool_pattern.search(text)

            if match:
                tool_name = match.group(1)
                server_name = match.group(2)
                logger.info(f"Found tool: {tool_name} from server: {server_name}")
                return tool_name, server_name

        except Exception as e:
            logger.error(f"Tesseract error: {e}")

        return None, None


class AutoApprover:
    """Automatically approves tool requests in the Claude desktop app on macOS.

    This class detects and processes approval requests from the Claude application,
    particularly focusing on tool usage requests. It handles window detection, OCR,
    pattern matching for allowed tools, and UI automation to click approval buttons.

    Attributes:
        config: Configuration singleton with settings.
        template_manager: Manager for image templates used in recognition.
        window_manager: Manager for Claude window interaction.
        ocr_service: Service for optical character recognition.
        previous_foreground_app: Stores information about the previously focused app.
    """

    def __init__(self) -> None:
        """Initialize AutoApprover with required services and managers."""
        self.config = Config()
        self.template_manager = TemplateManager()
        self.window_manager = WindowManager()
        self.ocr_service = OCRService()
        self.previous_foreground_app = None

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if the requested tool is in the allowed list.

        Args:
            tool_name: Name of the tool being requested.

        Returns:
            bool: True if the tool is allowed, False otherwise.
        """
        return tool_name in self.config.allowed_tools

    def find_and_click_button(
        self, screenshot: Image.Image, window_x: int, window_y: int
    ) -> Optional[bool]:
        """Find an approval button in a screenshot and click it.

        Uses template matching to locate the approval button, then calculates
        its screen position and simulates a click. Preserves mouse position
        after clicking. Also preserves and restores the previously focused window.

        Args:
            screenshot: Image of the Claude application window.
            window_x: X-coordinate of the Claude window on screen.
            window_y: Y-coordinate of the Claude window on screen.

        Returns:
            bool: False if button was not found.
            None: If button was found and clicked.
        """
        # Log sizes for debugging
        button_template = self.template_manager.approve_button_template
        logger.info(
            f"Button template size: {button_template.width}x{button_template.height}"
        )
        logger.info(f"Screenshot size: {screenshot.width}x{screenshot.height}")

        # Check template size
        if (
            button_template.width > screenshot.width
            or button_template.height > screenshot.height
        ):
            logger.error(
                f"Button template size ({button_template.width}x{button_template.height}) "
                f"is larger than screenshot ({screenshot.width}x{screenshot.height})"
            )
            return False

        try:
            button_location = pyautogui.locate(
                button_template, screenshot, confidence=self.config.confidence_threshold
            )
        except Exception as e:
            logger.error(f"Error locating button: {e}")
            return False

        if button_location:
            button_tuple = (
                button_location.left,
                button_location.top,
                button_location.width,
                button_location.height,
            )
            rel_x, rel_y = pyautogui.center(button_tuple)

            # Get window size information from the raw window bounds
            window_info = self.window_manager.get_window_info(
                self.window_manager.cached_window_id
            )
            _, _, window_width, window_height = window_info

            # Calculate the scaling factor for Retina displays
            # by comparing screenshot dimensions with window dimensions
            scale_x = screenshot.width / window_width
            scale_y = screenshot.height / window_height

            # Apply the scaling factor to the relative coordinates
            scaled_rel_x = rel_x / scale_x
            scaled_rel_y = rel_y / scale_y

            # Calculate the final screen position
            screen_x, screen_y = window_x + scaled_rel_x, window_y + scaled_rel_y

            # Log scaling information for debugging
            logger.info(f"Window size from bounds: {window_width}x{window_height}")
            logger.info(f"Screenshot size: {screenshot.width}x{screenshot.height}")
            logger.info(f"Calculated scaling factors: X={scale_x}, Y={scale_y}")
            logger.info(f"Button relative position: {rel_x}, {rel_y}")
            logger.info(f"Scaled relative position: {scaled_rel_x}, {scaled_rel_y}")

            # Save current mouse position
            old_x, old_y = pyautogui.position()

            # Save the currently focused app before switching
            self.previous_foreground_app = get_frontmost_app()
            if self.previous_foreground_app:
                logger.info(
                    f"Saving current foreground app: {self.previous_foreground_app['name']}"
                )

            # Focus Claude window to ensure click works properly
            self.window_manager.focus_claude_window()
            time.sleep(0.2)  # Short delay to ensure window is focused

            # Click the button
            logger.info(f"Button found at {screen_x}, {screen_y}")
            pyautogui.click(screen_x, screen_y)

            # Restore mouse position
            pyautogui.moveTo(old_x, old_y)

            # Restore the previously focused app
            if self.previous_foreground_app:
                logger.info(
                    f"Restoring previous foreground app: {self.previous_foreground_app['name']}"
                )
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

            return None
        else:
            return False

    def auto_approve(self) -> Tuple[bool, Optional[str]]:
        """Find the Claude window and approve allowed tool requests.

        Captures a screenshot of the Claude window, detects dialog boxes,
        extracts tool names using OCR, and clicks approval buttons for
        allowed tools. Tries dialog templates sequentially, only continuing
        to the next template if no tool name is found with the current one.

        Returns:
            Tuple[bool, Optional[str]]:
                - First value: Whether a button was found and clicked.
                - Second value: Reason code for failures or None on success.
                  Possible values: "no_window", "not_allowed", "image_not_found", "error"
        """
        try:
            claude_window_id, window_info = (
                self.window_manager.get_claude_window_with_cache()
            )

            if not claude_window_id:
                return False, "no_window"

            # We'll focus Claude when clicking the button, not here
            # This avoids unnecessarily switching focus during detection

            x, y, width, height = window_info
            # Pass window_id to capture method to use direct window capture without bounds
            # This should capture the entire window content regardless of occlusion
            screenshot = self.window_manager.capture_window_screenshot(
                0, 0, 0, 0, claude_window_id
            )
            dialog_found = False

            for idx, template in enumerate(self.template_manager.dialog_templates):
                # Check if template is smaller than screenshot
                if (
                    template.width > screenshot.width
                    or template.height > screenshot.height
                ):
                    logger.warning(
                        f"Template {idx + 1} size ({template.width}x{template.height}) is larger than screenshot ({screenshot.width}x{screenshot.height})"
                    )
                    continue

                try:
                    dialog_location = pyautogui.locate(
                        template,
                        screenshot,
                        confidence=self.config.dialog_confidence,
                        grayscale=True,
                    )
                except Exception as e:
                    logger.error(f"Error locating dialog with template {idx + 1}: {e}")
                    continue

                if dialog_location:
                    dialog_found = True
                    logger.info(f"Dialog found (template variant {idx + 1})")

                    x_roi, y_roi, w_roi, h_roi = dialog_location
                    padding = 20
                    x_roi_padded = max(0, x_roi - padding)
                    y_roi_padded = max(0, y_roi - padding)
                    w_roi_padded = min(
                        screenshot.width - x_roi_padded, w_roi + (2 * padding)
                    )
                    h_roi_padded = min(
                        screenshot.height - y_roi_padded, h_roi + (2 * padding)
                    )

                    padded_roi = (
                        x_roi_padded,
                        y_roi_padded,
                        w_roi_padded,
                        h_roi_padded,
                    )

                    tool_name, server_name = self.ocr_service.extract_tool_info(
                        screenshot, padded_roi
                    )

                    if tool_name:
                        logger.info(
                            f"Tool name found with dialog template {idx + 1}: {tool_name}"
                        )
                        if self.is_tool_allowed(tool_name):
                            logger.info(
                                f"Tool {tool_name} is allowed, clicking approve button"
                            )
                            button_clicked = self.find_and_click_button(
                                screenshot, x, y
                            )
                            return button_clicked, None
                        else:
                            logger.warning(
                                f"Tool {tool_name} not in allowed list, skipping approval"
                            )
                            return False, "not_allowed"
                    else:
                        logger.info(
                            f"No tool name found with dialog template {idx + 1}, trying next template if available"
                        )

            if dialog_found:
                logger.warning(
                    "Dialog found but couldn't extract tool name from any template"
                )
            return False, None

        except pyautogui.ImageNotFoundException:
            return False, "image_not_found"
        except Exception as e:
            logger.error(f"Error in auto_approve: {e}")
            return False, "error"

    def debug_capture(self) -> None:
        """Capture a single screenshot and save debug information.

        This method:
        1. Creates a debug directory if it doesn't exist
        2. Captures a screenshot of the Claude window
        3. Saves the screenshot
        4. Saves copies of all template images
        5. Creates an HTML report with all images for easy comparison
        """
        debug_dir = self.config.debug_dir
        debug_dir.mkdir(exist_ok=True)

        # Get window information
        claude_window_id, window_info = (
            self.window_manager.get_claude_window_with_cache()
        )

        if not claude_window_id:
            logger.error("Could not find Claude window for debug capture")
            return

        # Capture screenshot
        x, y, width, height = window_info
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        logger.info(
            f"Capturing debug screenshot of window at {x},{y} with size {width}x{height}"
        )

        # NOTE: Focusing code is disabled as requested
        # self.window_manager.focus_claude_window()
        # Short delay to ensure window is fully in foreground
        # time.sleep(0.5)

        # Capture screenshots using both methods for comparison
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        logger.info(
            f"Capturing debug screenshots of window at {x},{y} with size {width}x{height}"
        )

        # Capture using direct window method (passing 0,0,0,0 to use CGRectNull)
        direct_screenshot = self.window_manager.capture_window_screenshot(
            0, 0, 0, 0, claude_window_id
        )
        direct_screenshot_path = debug_dir / f"screenshot-direct-{timestamp}.png"
        direct_screenshot.save(direct_screenshot_path)
        logger.info(f"Saved direct-capture screenshot to {direct_screenshot_path}")

        # Also capture using traditional screen method for comparison
        screen_screenshot = self.window_manager.capture_window_screenshot(
            x, y, width, height
        )
        screen_screenshot_path = debug_dir / f"screenshot-screen-{timestamp}.png"
        screen_screenshot.save(screen_screenshot_path)
        logger.info(f"Saved screen-capture screenshot to {screen_screenshot_path}")

        # Use the direct method for further processing
        screenshot = direct_screenshot
        screenshot_path = direct_screenshot_path

        # Save copies of template images
        button_template_path = debug_dir / f"button_template-{timestamp}.png"
        self.template_manager.approve_button_template.save(button_template_path)

        dialog_template_paths = []
        for idx, template in enumerate(self.template_manager.dialog_templates):
            path = debug_dir / f"dialog_template-{idx + 1}-{timestamp}.png"
            template.save(path)
            dialog_template_paths.append(path)

        # Create HTML report
        html_report_path = debug_dir / f"debug_report-{timestamp}.html"
        with open(html_report_path, "w") as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Claude Auto-Approve Debug Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        .image-container {{ display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }}
        .image-item {{ border: 1px solid #ddd; padding: 10px; }}
        .image-caption {{ text-align: center; margin-top: 10px; font-weight: bold; }}
        img {{ max-width: 500px; max-height: 500px; }}
        .meta {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Claude Auto-Approve Debug Report</h1>
    <div class="meta">
        <p><strong>Timestamp:</strong> {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>Window Size:</strong> {width}x{height}</p>
        <p><strong>Window Position:</strong> ({x}, {y})</p>
        <p><strong>Button Template Size:</strong> {self.template_manager.approve_button_template.width}x{self.template_manager.approve_button_template.height}</p>
        <p><strong>Confidence Threshold:</strong> {self.config.confidence_threshold}</p>
        <p><strong>Dialog Confidence Threshold:</strong> {self.config.dialog_confidence}</p>
    </div>
    
    <h2>Window Screenshots (Comparison)</h2>
    <div class="image-container">
        <div class="image-item">
            <img src="{direct_screenshot_path.name}" alt="Direct Window Capture">
            <div class="image-caption">Direct Window Capture (CGWindowListCreateImage)</div>
        </div>
        <div class="image-item">
            <img src="{screen_screenshot_path.name}" alt="Screen Capture">
            <div class="image-caption">Screen Capture (MSS)</div>
        </div>
    </div>
    
    <h2>Button Template</h2>
    <div class="image-container">
        <div class="image-item">
            <img src="{button_template_path.name}" alt="Button Template">
            <div class="image-caption">Approve Button Template</div>
        </div>
    </div>
    
    <h2>Dialog Templates</h2>
    <div class="image-container">
""")

            for idx, path in enumerate(dialog_template_paths):
                f.write(f"""
        <div class="image-item">
            <img src="{path.name}" alt="Dialog Template {idx + 1}">
            <div class="image-caption">Dialog Template {idx + 1}</div>
        </div>""")

            f.write("""
    </div>
</body>
</html>""")

        logger.info(f"Created HTML debug report: {html_report_path}")

        # Try to open the report in the default browser
        try:
            import webbrowser

            webbrowser.open(str(html_report_path))
            logger.info("Opened debug report in browser")
        except Exception as e:
            logger.error(f"Failed to open debug report in browser: {e}")
            logger.info(f"Please open the debug report manually: {html_report_path}")

    def run(self):
        """Main execution loop with dynamic delay between checks.

        Continuously monitors for approval requests with adaptive delay times
        based on detection results. Runs until interrupted by user with Ctrl+C.

        Exits if Tesseract OCR is not properly configured.
        """
        if not self.ocr_service.configure_ocr():
            logger.error(
                "Cannot continue without Tesseract OCR. Please install it with 'brew install tesseract'"
            )
            sys.exit(1)

        logger.info(
            f"Starting auto-approval script for {self.config.claude_window_title}"
        )

        # If debug mode is enabled, just do a single capture and exit
        if self.config.debug_mode:
            logger.info(
                "Running in debug mode - will capture a single screenshot and exit"
            )
            self.debug_capture()
            logger.info("Debug capture complete. Exiting.")
            return

        print("Press Ctrl+C to stop the script")
        current_delay = self.config.normal_delay

        try:
            while True:
                result, reason = self.auto_approve()

                if reason == "no_window":
                    logger.info("Claude window not found")
                    current_delay = self.config.no_window_delay
                elif reason == "image_not_found":
                    logger.info("Approve button not found")
                    current_delay = self.config.no_image_delay
                elif reason == "not_allowed":
                    logger.info("Tool not allowed")
                    current_delay = self.config.blocked_tool_delay
                else:
                    current_delay = self.config.normal_delay

                logger.info(f"Waiting {current_delay} seconds before next check")
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
        help="Run in debug mode (capture single screenshot and exit)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        help="Button template matching confidence threshold (0.0-1.0)",
    )
    parser.add_argument(
        "--dialog-confidence",
        type=float,
        help="Dialog template matching confidence threshold (0.0-1.0)",
    )
    parser.add_argument(
        "--app-name", type=str, help="Claude application name to look for"
    )
    parser.add_argument(
        "--list-windows", action="store_true", help="List all windows and exit"
    )
    args = parser.parse_args()

    # Initialize configuration
    config = Config()

    # Apply command-line overrides
    if args.debug:
        config.debug_mode = True
    if args.confidence is not None:
        config.confidence_threshold = args.confidence
    if args.dialog_confidence is not None:
        config.dialog_confidence = args.dialog_confidence
    if args.app_name is not None:
        config.claude_app_name = args.app_name

    # Special mode to just list all windows
    if args.list_windows:
        window_manager = WindowManager()
        window_manager.list_all_windows()
        return

    auto_approver = AutoApprover()
    auto_approver.run()


if __name__ == "__main__":
    main()
