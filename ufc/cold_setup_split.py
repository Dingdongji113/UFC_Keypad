# -*- coding: utf-8 -*-
"""Split cold-start setup LAND/CV into independent LAND and CV buttons.

Installed after ``install_cold_direct_entry``.  The base cold-start layer keeps a
single LAND/CV toggle for backward compatibility; this patch replaces only the
setup-page control layout and click handling so the user sees four independent
setup choices:

    DAY  NIGHT  LAND  CV

Checklist behavior stays unchanged: the setup page still requires START twice,
text remains unboxed, checklist still uses the large centered START plus the
small lower-right RESET.
"""
from __future__ import annotations

from ufc.cold_direct_entry import (
    ENTRY_CHECKLIST,
    ENTRY_SETUP,
    PAGE,
    P_DAY,
    P_NIGHT,
    P_RESET,
    P_START,
    RESET_TAP_WINDOW_SEC,
)

P_LAND = (300, 6)
P_CV = (300, 8)


def install_split_land_cv_setup(UFCKeypadWindowClass) -> None:
    """Patch cold-start setup controls so LAND and CV are separate buttons."""
    if getattr(UFCKeypadWindowClass, "_cold_split_land_cv_installed", False):
        return
    UFCKeypadWindowClass._cold_split_land_cv_installed = True

    def _init_cold_start_page(self):
        """Create no-frame text layout plus DAY/NIGHT/LAND/CV, START, RESET."""
        self._cold_cells = {}
        self._cold_status_cells = {}

        self._cold_plain_label("title", 8, 20, 1008, 58, 31, True)
        self._cold_plain_label("rpm", 8, 100, 1008, 70, 29, True)
        self._cold_plain_label("step", 8, 196, 1008, 86, 28, True)
        self._cold_plain_label("hint", 80, 302, 864, 72, 18, False)
        self._cold_plain_label("status", 8, 378, 1008, 34, 13, False)

        setup_buttons = [
            ("DAY", P_DAY, 152, 430, 138, 58),
            ("NIGHT", P_NIGHT, 302, 430, 158, 58),
            ("LAND", P_LAND, 472, 430, 138, 58),
            ("CV", P_CV, 622, 430, 116, 58),
        ]
        for text, pos, x, y, w, h in setup_buttons:
            cell = self.place_cell(text, pos, x, y, w, h, font_size=15,
                                   register=False, page=PAGE, bold=True)
            self._cold_cells[pos] = cell

        start = self.place_cell("START", P_START, 312, 505, 400, 82,
                                font_size=25, register=False, page=PAGE, bold=True)
        self._cold_cells[P_START] = start

        reset = self.place_cell("RESET", P_RESET, 884, 545, 132, 42,
                                font_size=12, register=False, page=PAGE, bold=True)
        self._cold_cells[P_RESET] = reset
        self._cold_refresh_ui()

    def _cold_handle_click(self, pos):
        if pos in ((0, 0), (1, 0)):
            max_rpm = self._cold_max_rpm()
            if self._cold_state in ("complete", "aborted") or (max_rpm is not None and max_rpm >= self._cold_rpm_threshold):
                self._show_page("local_icp")
            else:
                self._cold_last_action = "LOCAL ICP LOCKED"
                self._cold_step_detail = "Cold-start manager has priority."
            self._cold_refresh_ui()
            return
        if pos == P_START:
            self._cold_arm_or_continue()
        elif pos == P_RESET:
            self._cold_handle_reset_tap()
        elif pos == P_DAY:
            self._cold_set_display_mode("day")
        elif pos == P_NIGHT:
            self._cold_set_display_mode("night")
        elif pos == P_LAND:
            self._cold_set_profile("land")
        elif pos == P_CV:
            self._cold_set_profile("carrier")
        self._cold_refresh_ui()

    def _cold_refresh_ui(self):
        cells = getattr(self, "_cold_status_cells", {})
        if not cells:
            return
        lines = self._cold_status_lines()
        for key, text in lines.items():
            self._cold_set_cell(key, text)

        is_page = getattr(self, "_current_page", None) == PAGE
        in_setup = getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_CHECKLIST
        waiting_for_rpm = self._cold_detected_mode == "unknown" and not getattr(self, "_cold_first_mode_decided", False)
        for pos in (P_DAY, P_NIGHT, P_LAND, P_CV):
            cell = getattr(self, "_cold_cells", {}).get(pos)
            if cell:
                cell.setVisible(is_page and in_setup and not waiting_for_rpm)
        reset = getattr(self, "_cold_cells", {}).get(P_RESET)
        if reset:
            reset.setVisible(is_page and not in_setup and not waiting_for_rpm)
        start = getattr(self, "_cold_cells", {}).get(P_START)
        if start:
            start.setVisible(is_page and not waiting_for_rpm)

    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
