"""Which newspad's file a design panel writes, and when it writes it.

The press cover, the dossier cover and the two headline-style panels are each
one newspad's own. There is still one copy of each panel in the window - two
copies each saving the whole file is the measured hazard that ruled out four
windows - so a newspad switch points each panel at the other newspad's file.
Everything that can go wrong goes wrong at that moment, so the rules live here,
once, rather than three times:

*   A panel's file is part of the panel, never worked out from "the newspad
    that is open" at save time. A save armed before a switch would otherwise
    land in the newspad the switch goes to.
*   Pending edits are written to the file being LEFT before the panel moves.
*   A load never saves, and nothing a load does can arm a save.
*   A save is armed only when the DESIGN actually changed. A cover's date, its
    count and the dossier's division lines are the newspad's own values and
    live in its session - moving the date must not rewrite the cover design,
    or a design file that cannot be written would trap somebody in a newspad
    for changing the day.
*   Every write is whole or nothing (newspads.write_design).
*   A file that is there but will not read is never written over and never
    copied into another newspad as if it were a design. It is set aside -
    renamed, never deleted - only when somebody changes that design, and their
    change is then saved.
*   A newspad seen for the first time is given a copy of the design in memory,
    and only if that design can be trusted.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core import newspads

#: A design file read while something else is writing it - OneDrive, an
#: antivirus scanner, an older copy of the program - can fail once and read
#: fine a moment later. It is tried a few times before it is called unreadable.
READ_TRIES = 3
READ_PAUSE = 0.05


class DesignFile:
    """Mixed into CoverCard, SentimentCoverCard and HeadingLayoutCard.

    Each supplies: design_name, _save_timer, _root_file(), _design_state(),
    _take_design(data) and, optionally, _design_dump(state) and _repaint_now().
    """

    design_name = ""

    def _init_design(self) -> None:
        self._path: Optional[Path] = None    # None: Newspad 1's own file
        self._held = False                   # saving nothing at all
        self._dirty = False                  # an edit is waiting to be written
        self._unreadable = False             # there, but will not read
        # Showing the defaults only because nothing trustworthy could be copied
        # into a new newspad. Not a design anybody chose: never copied, never
        # written out as this newspad's look, until somebody changes it.
        self._placeholder = False
        self._saved: Optional[dict] = None   # the design as last read or written
        self.problem = ""                    # last thing that went wrong, said once

    # -------------------------------------------------------------- hooks
    def _root_file(self) -> Path:
        raise NotImplementedError

    def _design_state(self) -> dict:
        raise NotImplementedError

    def _take_design(self, data: dict) -> None:
        """Put a parsed design (or {} for the defaults) on screen. No saving."""
        raise NotImplementedError

    def _design_dump(self, state: dict) -> str:
        return json.dumps(state, indent=2, ensure_ascii=False)

    def _repaint_now(self) -> None:
        pass

    # -------------------------------------------------------------- where
    def design_file(self) -> Path:
        return self._path if self._path is not None else self._root_file()

    def file_for(self, number: int) -> Path:
        """This panel's file in the given newspad. Newspad 1's comes from the
        same place it always has, so a bare panel is Newspad 1's panel."""
        if number == 1:
            return self._root_file()
        return newspads.design_file(number, self.design_name)

    @property
    def trusted(self) -> bool:
        """Whether what is on screen may be copied into another newspad, or
        written out as this newspad's look without anybody having changed it."""
        return not (self._held or self._unreadable or self._placeholder)

    # ------------------------------------------------------------ writing
    def _changed_design(self) -> None:
        """Somebody changed something. Save shortly - if the design moved."""
        if self._design_state() == self._saved:
            return
        self._placeholder = False        # a change is a design somebody chose
        self._dirty = True
        self._save_timer.start()

    def _say(self, message: str) -> None:
        self.problem = message
        signal = getattr(self, "designProblem", None)
        if signal is not None:
            try:
                signal.emit(message)
            except RuntimeError:
                pass

    def _set_bad_file_aside(self) -> bool:
        """Rename an unreadable design file out of the way. Never deletes."""
        path = self.design_file()
        if not path.exists():
            self._unreadable = False
            return True
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            os.replace(path, path.with_name(f"{path.name}.unreadable-{stamp}"))
        except OSError:
            return False
        self._unreadable = False
        return True

    def save(self, strict: bool = False, to=None) -> bool:
        """Write the design. To its own file, or to ``to`` (a copy for a newspad
        seen for the first time). Returns whether anything was written.

        ``strict`` is for a switch: a failure raises, so the switch can be
        refused rather than go ahead and drop an edit without a word.
        """
        own = to is None
        target = self.design_file() if own else Path(to)
        if own and self._held:
            return False
        if own and self._unreadable and not self._set_bad_file_aside():
            message = (f"{target.name} could not be read or set aside, so this "
                       f"change was not saved.")
            self._say(message)
            if strict:
                raise OSError(message)
            return False
        state = self._design_state()
        try:
            newspads.write_design(target, self._design_dump(state))
        except Exception as error:  # noqa: BLE001 - settings are a convenience
            if strict:
                raise
            self._say(f"{target.name} could not be saved ({error}).")
            return False
        if own:
            self._dirty = False
            self._saved = state
        return True

    def flush(self, strict: bool = False) -> None:
        """Write whatever the debounce is still holding - to this panel's file."""
        if not (self._save_timer.isActive() or self._dirty):
            return
        self._save_timer.stop()
        try:
            self.save(strict=strict)
        except Exception:
            self._save_timer.start()     # kept, and tried again later
            raise

    def drop_pending(self) -> None:
        """Give up on an edit that cannot be written - asked for, never silent."""
        self._save_timer.stop()
        self._dirty = False

    def hold(self) -> None:
        """Save nothing more until the panel is pointed somewhere again."""
        self._save_timer.stop()
        self._held = True

    # ------------------------------------------------------------ reading
    def _read_design(self) -> tuple[dict, str]:
        """(data, "clean" | "missing" | "bad"). Never raises."""
        path = self.design_file()
        if not path.exists():
            return {}, "missing"
        for attempt in range(READ_TRIES):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                if attempt + 1 < READ_TRIES:
                    time.sleep(READ_PAUSE)
                continue
            return (data, "clean") if isinstance(data, dict) else ({}, "bad")
        return {}, "bad"

    def load(self) -> None:
        """Read this panel's file and show it. Never saves, never arms a save.

        Anything the debounce still held is DROPPED - whoever moves the panel
        flushes first. A missing file shows the defaults and may be written
        later; an unreadable one shows the defaults and is never written over
        until somebody changes the design (see _set_bad_file_aside).
        """
        self._save_timer.stop()
        data, how = self._read_design()
        self._unreadable = how == "bad"
        self._placeholder = False
        self._take_design(data)
        self._saved = self._design_state()
        self._dirty = False
        if how == "bad":
            # Noted, not announced: the window says it once, naming the newspad
            # and the panel, when it points the panels somewhere.
            self.problem = (f"{self.design_file().name} could not be read, so "
                            f"this panel shows its defaults. The file is kept.")

    def reload(self) -> None:
        self.load()
        self._repaint_now()

    def adopt(self, path, seed: bool) -> bool:
        """Point this panel at another newspad's file. Synchronous, no events.

        1. Anything pending is written to the file being LEFT.
        2. The panel moves.
        3. The new file is loaded - or, if it is not there and ``seed`` is
           asked for, the design on screen is written there as its first copy,
           but only a design that can be trusted. Returns True for a copy.

        If loading fails the panel is held, so it cannot write the design it
        still shows into the file it now points at.
        """
        try:
            self.flush()
        except Exception:  # noqa: BLE001 - the old file; kept dirty, said once
            pass
        self._save_timer.stop()
        self._path = Path(path)
        try:
            missing = not self._path.exists()
            if seed and missing and self.trusted:
                self.save(to=self._path, strict=True)
                self._saved = self._design_state()
                self._dirty = False
                self._held = False
                self._repaint_now()
                return True
            self._held = False
            self.reload()
            # Nothing trustworthy to copy into a newspad that has no look yet:
            # it shows the defaults, and they are NOT its look. Written out,
            # they would stop a proper copy ever being made.
            self._placeholder = seed and missing
        except Exception:
            self.hold()
            raise
        return False
