"""The browser's ☰ side panel: which sites it is signed in to, and what they keep.

The person asked to see "the credentials I stored" and remove them. What a
browser of the program's own keeps is cookies - a site keeps somebody signed
in with one - and never a password: Qt's engine has no password store, and the
program never sees a password, which is typed into the site's own page. So the
panel says that plainly, and lists what there is:

*   **Signed in** - by the name of each site's sign-in cookie - with Sign out.
*   **Sites that keep data** - every site, its cookie count and the date its
    data lasts until, the cookie NAMES on hover. Never a value: the panel is
    built from core/sitedata.CookieFact, which has no field for one.
*   **Permissions** the sites asked for (the browser refuses them), with Forget.
*   **The program's own Chrome** - the hidden Chrome that captures when the
    browser inside the app cannot - with its sign-ins and Sign out. Never the
    person's everyday Chrome.
*   Clear stored pages and pictures, forget visited pages, remove everything.
    A page's own saved data (local storage) is removed the next time the
    program starts: the engine keeps those files locked while it runs, and
    has no way to clear them site by site.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import sitedata, webshot
from . import theme

PASSWORDS_NOTE = ("No passwords are stored here. This browser saves none, and the "
                  "program never sees one - you type it into the site's own page. A "
                  "site keeps you signed in with a cookie, listed below; Sign out "
                  "removes it, and your password is unchanged. Passwords saved in "
                  "your own Chrome are never read.")
STORAGE_NOTE = ("Signed out of every site; stored pages, visited pages and "
                "permissions are cleared. What pages saved for themselves (local "
                "storage) goes the next time the program starts - the browser keeps "
                "it locked while it runs.")
CHROME_NOTE = ("The program's own hidden Chrome captures when the browser inside the "
               "app cannot. Its sign-ins are listed here; your everyday Chrome is "
               "never read or touched.")
#: While the program's Chrome is open its cookie file is locked to it, and a
#: read of it gets nothing - which the panel used to call "It keeps nothing".
CHROME_OPEN = ("The program's Chrome is open now, so what it keeps cannot be read. "
               "Its sign-ins show here once it is closed.")
CHROME_OPEN_KEPT = ("The program's Chrome is open now: this is what it kept when it was "
                    "last looked at.")

_PERMISSION_NAMES = {
    "Notifications": "Notifications", "Geolocation": "Location",
    "ClipboardReadWrite": "Clipboard", "MediaAudioCapture": "Microphone",
    "MediaVideoCapture": "Camera", "MediaAudioVideoCapture": "Camera and microphone",
    "DesktopVideoCapture": "Screen", "DesktopAudioVideoCapture": "Screen and sound",
    "MouseLock": "Mouse lock", "LocalFontsAccess": "Fonts",
}


def _day(when) -> str:
    if when is None:
        return "until the browser closes"
    try:
        return "until " + when.astimezone().strftime("%d %b %Y").lstrip("0")
    except Exception:  # noqa: BLE001
        return ""


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SideHeading")
    return label


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.MUTED};")
    return label


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class SitePanel(QFrame):
    """What the browser inside the app keeps, and the buttons that remove it.

    Filled when it is shown, and then only from the jar as cookies come and
    go - never while it is hidden. A news page sets cookies all the time it
    loads, and each fill used to go over the whole jar once per site, read the
    program's Chrome's cookie file again, and run in every panel of every
    browser window ever opened, hidden or not: a second at a time on a
    well-used profile, on the thread that answers the captures (review of
    step B). The site somebody has chosen, and the sites they opened, stay
    chosen and open through a fill."""

    #: A sign-in page for the browser window to open.
    openAddress = Signal(str)

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self.host = host
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)
        self.sign_out_buttons: dict = {}
        self.sign_in_buttons: dict = {}
        self.forget_buttons: list = []
        self.chrome_sign_out_buttons: dict = {}
        #: The jar as last read: its sites' cookies, and one line per site.
        self._grouped: dict = {}
        self._summary: list = []
        #: Who was signed in when the Signed in rows were last made.
        self._signed_key = None
        #: How many times the jar was read to fill the panel - for the suites.
        self.fills = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)
        self.header = QLabel()
        self.header.setStyleSheet(f"font-weight: 700; color: {theme.INK};")
        self.header.setWordWrap(True)
        outer.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(6)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        lay.addWidget(_heading("Signed in"))
        self.signed_box = QVBoxLayout()
        self.signed_box.setSpacing(4)
        lay.addLayout(self.signed_box)
        self.passwords = _muted(PASSWORDS_NOTE)
        lay.addWidget(self.passwords)

        lay.addWidget(_heading("Sites that keep data"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a site")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._fill_tree)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Site", "Cookies", "Kept"])
        self.tree.setRootIsDecorated(True)
        self.tree.setMinimumHeight(220)
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 56)
        self.tree.itemSelectionChanged.connect(self._sync_remove)
        # A site's cookies are listed when it is opened, not for every site on
        # every fill: a jar holds thousands of them.
        self.tree.itemExpanded.connect(self._fill_children)
        lay.addWidget(self.tree)
        self.remove = QPushButton("Remove this site's data")
        self.remove.setEnabled(False)
        self.remove.clicked.connect(self._remove_selected)
        lay.addWidget(self.remove, 0, Qt.AlignLeft)
        QShortcut(QKeySequence(Qt.Key_Delete), self.tree, self._remove_selected,
                  context=Qt.WidgetShortcut)

        self.permissions_heading = _heading("Permissions")
        lay.addWidget(self.permissions_heading)
        self.permissions_box = QVBoxLayout()
        self.permissions_box.setSpacing(4)
        lay.addLayout(self.permissions_box)

        lay.addWidget(_heading("The program's own Chrome"))
        lay.addWidget(_muted(CHROME_NOTE))
        self.chrome_box = QVBoxLayout()
        self.chrome_box.setSpacing(4)
        lay.addLayout(self.chrome_box)
        lay.addStretch(1)

        self.clear_cache = QPushButton("Clear stored pages and pictures")
        self.forget_visited = QPushButton("Forget visited pages")
        self.forget_all = QPushButton("Remove everything…")
        self.forget_all.setObjectName("LinkDanger")
        for button in (self.clear_cache, self.forget_visited, self.forget_all, self.remove):
            button.setCursor(Qt.PointingHandCursor)
        self.clear_cache.clicked.connect(self._clear_cache)
        self.forget_visited.clicked.connect(self._forget_visited)
        self.forget_all.clicked.connect(self._forget_all)
        outer.addWidget(self.clear_cache)
        outer.addWidget(self.forget_visited)
        outer.addWidget(self.forget_all)
        self.note = _muted("")
        outer.addWidget(self.note)

        # Bound methods, never lambdas: the host outlives every panel, and a
        # lambda would still be called on a panel that has gone.
        host.jarChanged.connect(self._jar_changed)
        if hasattr(host, "cacheCleared"):
            host.cacheCleared.connect(self._cache_cleared)
        if hasattr(host, "signOutLeft"):
            host.signOutLeft.connect(self._left_over)

    # ---------------------------------------------------------------- build
    def showEvent(self, event):  # noqa: N802 - Qt's name
        super().showEvent(event)
        self.rebuild()

    def rebuild(self) -> None:
        """Everything read again: when the panel is shown, and after Remove
        everything. The program's Chrome and the permissions are read only
        here, never on a cookie change."""
        self._signed_key = None
        self._fill_host()
        self._fill_permissions()
        self._fill_chrome()

    def _jar_changed(self) -> None:
        """A cookie came or went. A hidden panel does nothing: it is filled
        when it is next shown."""
        if self.isVisible():
            self._fill_host()

    def _fill_host(self) -> None:
        """The header, Signed in and the sites - from one pass over the jar."""
        self.fills += 1
        self._grouped = self.host.jar.by_site()
        self._summary = summary = self.host.jar.summary(grouped=self._grouped)
        signed = [line for line in summary if line.signed_in]
        cookies = sum(line.count for line in summary)
        self.header.setText(
            f"{len(summary)} site{'s' if len(summary) != 1 else ''} keep{'s' if len(summary) == 1 else ''} "
            f"{cookies} cookie{'s' if cookies != 1 else ''} · {len(signed)} signed in")
        self._fill_signed(signed)
        self._fill_tree()

    def _fill_signed(self, signed: list) -> None:
        # Made again only when who is signed in changed, so a Sign out button
        # is not swapped for another under the pointer as a page loads.
        key = tuple((line.site, line.signed_in_until) for line in signed)
        if key == self._signed_key:
            return
        self._signed_key = key
        _clear(self.signed_box)
        self.sign_out_buttons, self.sign_in_buttons = {}, {}
        for line in signed:
            row = QHBoxLayout()
            words = QLabel(f"{line.title} ({line.site}) — signed in, {_day(line.signed_in_until)}")
            words.setWordWrap(True)
            row.addWidget(words, 1)
            button = QPushButton("Sign out")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, s=line.site: self.sign_out(s))
            row.addWidget(button)
            self.signed_box.addLayout(row)
            self.sign_out_buttons[line.site] = button
        if not signed:
            self.signed_box.addWidget(_muted("Not signed in to any site."))
        known = {line.site for line in signed}
        for site, address in sitedata.LOGIN_PAGES.items():
            if site in known:
                continue
            button = QPushButton(f"Sign in to {sitedata.name_of(site)}")
            button.setObjectName("LinkNavy")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, a=address: self.openAddress.emit(a))
            self.signed_box.addWidget(button, 0, Qt.AlignLeft)
            self.sign_in_buttons[site] = button

    def _fill_tree(self, *_args) -> None:
        """The sites, from the jar as last read. What was chosen, which sites
        were open and how far the list was scrolled are put back: a page
        loading beside the panel sets cookies all the time, and every fill
        used to clear the choice and switch Remove off under the pointer."""
        wanted = self.filter.text().strip().lower()
        current = self.tree.currentItem()
        chosen = self._selected_site()
        chosen_name = current.text(0) if current is not None and current.parent() is not None else ""
        opened = set()
        for n in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(n)
            if top.isExpanded():
                opened.add(top.data(0, Qt.UserRole))
        scrolled = self.tree.verticalScrollBar().value()
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            again = None
            for line in self._summary:
                if wanted and wanted not in line.site:
                    continue
                item = QTreeWidgetItem([line.site, str(line.count), _day(line.until)])
                item.setData(0, Qt.UserRole, line.site)
                item.setToolTip(0, ", ".join(line.names))
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                if line.signed_in:
                    item.setText(0, f"{line.site}  ✓")
                self.tree.addTopLevelItem(item)
                if line.site in opened:
                    self._fill_children(item)
                    item.setExpanded(True)
                if line.site == chosen:
                    again = item
            if again is not None:
                if chosen_name:
                    self._fill_children(again)
                    again = next((again.child(c) for c in range(again.childCount())
                                  if again.child(c).text(0) == chosen_name), again)
                self.tree.setCurrentItem(again)
            self.tree.verticalScrollBar().setValue(scrolled)
        finally:
            self.tree.setUpdatesEnabled(True)
        self._sync_remove()

    def _fill_children(self, item) -> None:
        """One site's cookies, by name and date, the first time it is opened."""
        if item is None or item.parent() is not None or item.childCount():
            return
        site = str(item.data(0, Qt.UserRole) or "")
        for fact in sorted(self._grouped.get(site, ()), key=lambda f: f.name):
            child = QTreeWidgetItem([fact.name, "", _day(fact.expires)])
            child.setData(0, Qt.UserRole, site)
            child.setToolTip(0, f"{fact.name} on {fact.domain}{fact.path}")
            item.addChild(child)

    def _fill_permissions(self) -> None:
        _clear(self.permissions_box)
        self.forget_buttons = []
        try:
            permissions = list(self.host.permissions())
        except Exception:  # noqa: BLE001
            permissions = []
        self.permissions_heading.setVisible(bool(permissions))
        for permission in permissions:
            try:
                kind = _PERMISSION_NAMES.get(permission.permissionType().name,
                                             permission.permissionType().name)
                state = permission.state().name
                origin = permission.origin().host() or permission.origin().toString()
            except Exception:  # noqa: BLE001
                continue
            said = {"Granted": "allowed", "Denied": "blocked"}.get(state, "asks")
            row = QHBoxLayout()
            words = QLabel(f"{kind} — {said} for {origin}")
            words.setWordWrap(True)
            row.addWidget(words, 1)
            button = QPushButton("Forget")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, p=permission: self._forget_permission(p))
            row.addWidget(button)
            self.permissions_box.addLayout(row)
            self.forget_buttons.append((permission, button))

    def _fill_chrome(self) -> None:
        _clear(self.chrome_box)
        self.chrome_sign_out_buttons = {}
        try:
            lines, open_now = webshot.chrome_kept()
        except Exception:  # noqa: BLE001
            lines, open_now = [], False
        if open_now:
            self.chrome_box.addWidget(_muted(CHROME_OPEN_KEPT if lines else CHROME_OPEN))
        signed = [line for line in lines if line.signed_in]
        for line in signed:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{line.title} — signed in"), 1)
            button = QPushButton("Sign out")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, s=line.site: self.chrome_sign_out(s))
            row.addWidget(button)
            self.chrome_box.addLayout(row)
            self.chrome_sign_out_buttons[line.site] = button
        if lines:
            count = sum(line.count for line in lines)
            self.chrome_box.addWidget(_muted(f"{len(lines)} site{'s' if len(lines) != 1 else ''} "
                                             f"keep {count} cookie{'s' if count != 1 else ''} there."))
            button = QPushButton("Remove all of its sign-ins and data")
            button.setObjectName("LinkNavy")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda: self.chrome_sign_out(""))
            self.chrome_box.addWidget(button, 0, Qt.AlignLeft)
            self.chrome_sign_out_buttons[""] = button
        elif not open_now:
            self.chrome_box.addWidget(_muted("It keeps nothing."))

    # -------------------------------------------------------------- actions
    def sign_out(self, site: str) -> None:
        count = self.host.sign_out(site)
        self.note.setText(f"Signing out of {sitedata.name_of(site)} — {count} "
                          f"cookie{'s' if count != 1 else ''} removed.")

    def chrome_sign_out(self, site: str) -> None:
        done = webshot.sign_out_of_chrome(site)
        what = sitedata.name_of(site) if site else "every site"
        self.note.setText(f"The program's Chrome is signed out of {what}." if done == "done" else
                          f"The program's Chrome is open: it is signed out of {what} before it "
                          "next starts.")
        self._fill_chrome()

    def _cache_cleared(self) -> None:
        self.note.setText("Stored pages and pictures cleared.")

    def _left_over(self, site: str, count: int) -> None:
        self.note.setText(f"{count} cookie{'s' if count != 1 else ''} of {site} could not be "
                          "removed one by one - Remove everything takes them.")

    def _selected_site(self) -> str:
        item = self.tree.currentItem()
        return str(item.data(0, Qt.UserRole) or "") if item is not None else ""

    def _sync_remove(self) -> None:
        self.remove.setEnabled(bool(self._selected_site()))

    def _remove_selected(self) -> None:
        site = self._selected_site()
        if site:
            self.sign_out(site)

    def _forget_permission(self, permission) -> None:
        try:
            permission.reset()
        except Exception:  # noqa: BLE001
            pass
        self._fill_permissions()

    def _clear_cache(self) -> None:
        self.host.clear_cache()
        self.note.setText("Clearing stored pages and pictures…")

    def _forget_visited(self) -> None:
        self.host.forget_visited()
        self.note.setText("Visited pages forgotten.")

    def _forget_all(self) -> None:
        answer = QMessageBox.question(
            self, "Remove everything",
            "Remove everything the browser inside the app keeps - every sign-in, "
            "stored pages and pictures, visited pages and permissions? You will need "
            "to sign in again before posts that need it can be captured.")
        if answer != QMessageBox.Yes:
            return
        self.host.remove_everything()
        self.note.setText(STORAGE_NOTE)
        self.rebuild()
