"""Read native mouse state while the window manager owns a resize drag."""
import ctypes
import ctypes.util
import logging
import sys

from PyQt5.QtWidgets import QApplication


class NativeMouseButton:
    """Return None when no native reader is available so Qt remains the fallback."""
    def __init__(self):
        self.library = None
        self.display = None
        self.initialized = False
        self.backend = None

    def _initialize(self):
        self.initialized = True
        if sys.platform.startswith('linux') and QApplication.platformName() == 'xcb':
            name = ctypes.util.find_library('X11')
            if not name:
                raise OSError('X11 library unavailable')
            lib = ctypes.CDLL(name)
            lib.XOpenDisplay.argtypes, lib.XOpenDisplay.restype = [ctypes.c_char_p], ctypes.c_void_p
            lib.XCloseDisplay.argtypes, lib.XCloseDisplay.restype = [ctypes.c_void_p], ctypes.c_int
            lib.XScreenCount.argtypes, lib.XScreenCount.restype = [ctypes.c_void_p], ctypes.c_int
            lib.XRootWindow.argtypes, lib.XRootWindow.restype = [ctypes.c_void_p, ctypes.c_int], ctypes.c_ulong
            lib.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                *([ctypes.POINTER(ctypes.c_int)] * 4), ctypes.POINTER(ctypes.c_uint)]
            lib.XQueryPointer.restype = ctypes.c_int
            self.library, self.backend = lib, 'X11'
        elif sys.platform == 'darwin':
            name = ctypes.util.find_library('CoreGraphics')
            if not name:
                raise OSError('CoreGraphics unavailable')
            lib = ctypes.CDLL(name)
            lib.CGEventSourceButtonState.argtypes = [ctypes.c_int, ctypes.c_uint]
            lib.CGEventSourceButtonState.restype = ctypes.c_bool
            self.library, self.backend = lib, 'CoreGraphics'
        if self.backend:
            logging.debug('Window resize mouse-state backend: %s', self.backend)

    def pressed(self):
        try:
            if not self.initialized:
                self._initialize()
            if self.backend == 'CoreGraphics':
                return bool(self.library.CGEventSourceButtonState(0, 0))
            if self.backend == 'X11':
                return self._x11_pressed()
        except (AttributeError, OSError, TypeError, ValueError):
            logging.debug('Native resize mouse state unavailable; using Qt', exc_info=True)
            self.close()
            self.backend = None
        return None

    def _x11_pressed(self):
        lib = self.library
        if not self.display:
            self.display = lib.XOpenDisplay(None)
            if not self.display:
                raise OSError('Cannot open the X11 display')
        for screen in range(lib.XScreenCount(self.display)):
            root, child = ctypes.c_ulong(), ctypes.c_ulong()
            coordinates = [ctypes.c_int() for _ in range(4)]
            mask = ctypes.c_uint()
            if lib.XQueryPointer(self.display, lib.XRootWindow(self.display, screen),
                                 ctypes.byref(root), ctypes.byref(child),
                                 *(ctypes.byref(value) for value in coordinates), ctypes.byref(mask)):
                pressed = bool(mask.value & (1 << 8))  # X11 Button1Mask
                if not pressed:
                    self.close()
                return pressed
        return None

    def close(self):
        if self.display:
            self.library.XCloseDisplay(self.display)
            self.display = None
