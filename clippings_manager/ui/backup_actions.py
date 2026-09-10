"""Saving a setup, putting one back, and keeping a copy somewhere safe.

These live in a module of their own rather than on a screen, because two
different screens need them and one of those screens is not always there.

**The trap this exists to avoid.** The buttons started on the category editor,
which is opened from the Filter and arrange strip, which is on the select bar -
and the select bar hides itself when there are no clippings (`_update_counts`).
So on a machine with nothing imported yet, the whole chain was hidden, and
"Put a saved setup back" was unreachable on precisely the machine that needs to
put a setup back: a fresh install. Reaching them from the crown, which is always
on screen, is the fix; keeping them on the category editor too costs nothing and
is where somebody already editing their newspaper list would look.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..core import backup


def _keeping_folder() -> Path:
    from .export_dialog import keeping_folder

    return keeping_folder()


def save_setup(parent) -> bool:
    """Write everything this copy has been set up with to one file."""
    here = backup.what_is_here()
    if not here:
        QMessageBox.information(
            parent, "Nothing to save yet",
            "This copy has not been set up with anything of its own yet.\n\n"
            "Change a newspaper's category, teach the trainer something, or "
            "set up a cover, and there will be something to keep.")
        return False
    stamp = date.today().strftime("%Y%m%d")
    suggested = _keeping_folder() / f"ClippingsManager-setup-{stamp}.json"
    where, _picked = QFileDialog.getSaveFileName(
        parent, "Save my setup", str(suggested), "Setup file (*.json)")
    if not where:
        return False
    try:
        said = backup.save_to(where)
    except Exception as error:  # noqa: BLE001
        QMessageBox.warning(parent, "It could not be saved", str(error))
        return False
    QMessageBox.information(
        parent, "Saved",
        f"Written to:\n\n{where}\n\nIt carries:\n  · "
        + "\n  · ".join(said["what"])
        + "\n\nKeep this file. Opening it on another PC - or on this one after "
          "anything goes wrong - puts all of it back.\n\nYou do not need it to "
          "update the program: an update leaves your settings where they are.")
    return True


def load_setup(parent) -> bool:
    """Put a saved setup back, after saying exactly what that will do."""
    where, _picked = QFileDialog.getOpenFileName(
        parent, "Put a saved setup back", str(_keeping_folder()),
        "Setup file (*.json)")
    if not where:
        return False
    looked = backup.inspect(where)
    if not looked.get("ok"):
        QMessageBox.warning(parent, "That file cannot be used",
                            looked.get("why", "It could not be read."))
        return False

    lines = [f"That file was saved from version {looked.get('app', '?')} "
             f"on {(looked.get('saved') or '?')[:10]}.", "",
             "It will put back:", "  · " + "\n  · ".join(looked["coming"])]
    if looked["over"]:
        lines += ["", "Replacing what is set here now for:",
                  "  · " + "\n  · ".join(looked["over"])]
    lines += ["", "The clippings you are working on are not touched."]

    asked = QMessageBox(parent)
    asked.setIcon(QMessageBox.Question)
    asked.setWindowTitle("Put this setup back?")
    asked.setText("\n".join(lines))
    asked.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
    asked.setDefaultButton(QMessageBox.Cancel)
    if asked.exec() != QMessageBox.Yes:
        return False

    got = backup.restore_from(where)
    note = "Put back:\n  · " + "\n  · ".join(got.get("restored", []))
    if got.get("failed"):
        note += "\n\nCould not write:\n  · " + "\n  · ".join(got["failed"])
    note += ("\n\nThe newspaper list and anything taught to the trainer are in "
             "use straight away. If the window size was in the file, it takes "
             "effect next time the program starts.")
    QMessageBox.information(parent, "Done", note)
    return True


def choose_kept_folder(parent) -> bool:
    """Where to leave a copy of the setup every time the program closes."""
    now = backup.kept_where()
    places = backup.sync_places()

    asked = QMessageBox(parent)
    asked.setIcon(QMessageBox.Question)
    asked.setWindowTitle("Keep a copy of your setup")
    if now is not None:
        asked.setText(f"A copy is being kept in:\n\n{now}")
    else:
        asked.setText(
            "Every time you close the program, a copy of your setup can be "
            "written into a folder you choose.")
    asked.setInformativeText(
        "Point it at your Google Drive or OneDrive folder and the copy goes "
        "into your account by itself - the program never goes online, the sync "
        "program you already have does the carrying."
        + ("\n\nFound on this PC: " + ", ".join(said for said, _w in places)
           if places else
           "\n\nNo Google Drive or OneDrive folder found on this PC. Install "
           "Google Drive for Desktop and it will appear here, or choose any "
           "folder that is already backed up."))

    buttons = {}
    for said, where in places:
        buttons[asked.addButton(f"Use {said}", QMessageBox.AcceptRole)] = where
    browse = asked.addButton("Choose another folder…", QMessageBox.AcceptRole)
    stop = (asked.addButton("Stop keeping a copy", QMessageBox.DestructiveRole)
            if now is not None else None)
    asked.addButton(QMessageBox.Cancel)
    asked.exec()
    pressed = asked.clickedButton()

    if pressed is None or pressed is asked.button(QMessageBox.Cancel):
        return False
    if stop is not None and pressed is stop:
        backup.keep_copies_in(None)
        QMessageBox.information(
            parent, "Stopped",
            "No more copies will be written. The one already there is left "
            "where it is.")
        return True
    if pressed is browse:
        picked = QFileDialog.getExistingDirectory(
            parent, "Keep a copy in this folder", str(now or Path.home()))
        if not picked:
            return False
        where = Path(picked)
    else:
        where = buttons.get(pressed)
        if where is None:
            return False

    backup.keep_copies_in(where)
    written = backup.keep_a_copy()
    QMessageBox.information(
        parent, "A copy will be kept here",
        f"{where}\n\n"
        + (f"Written now as {written.name}.\n\n" if written else "")
        + "It is rewritten every time you close the program, always under the "
          "same name - your Drive or OneDrive keeps its own history, so an "
          "older copy can still be got back if it is ever needed."
        + "\n\nThe clippings you are working on are not copied there: they are "
          "a morning's work rather than a setting, and they are the "
          "newspapers' own pictures.")
    return True
