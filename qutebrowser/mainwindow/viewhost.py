# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Presentation host which shows one (or two) of the tabs it owns.

``QTabWidget``'s internal page stack can only show a single page, and a page
can't be in that stack and in a separate ``QSplitter`` at the same time. So the
``TabWidget`` keeps tab *identity* (order, indices, current tab) in its own
list and tab bar, and delegates tab *presentation* to this class.

Every tab widget is a permanent child of the host. Showing a different set of
tabs only toggles visibility (a ``QSplitter`` lays out visible children only),
so tab widgets are never reparented. That keeps the live page (and its
QtWebEngine state) untouched whether it is shown alone, next to another tab,
or hidden.
"""

from collections.abc import Sequence

from qutebrowser.qt.core import Qt
from qutebrowser.qt.widgets import QApplication, QSplitter, QWidget

from qutebrowser.utils import log


class ViewHost(QSplitter):

    """A splitter which owns all tab widgets and shows at most two of them.

    Attributes:
        _shown: The views currently shown, in display order.

    Class attributes:
        MAX_VIEWS: How many views can be shown at the same time.
    """

    MAX_VIEWS = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setChildrenCollapsible(False)
        self._shown: list[QWidget] = []

    def shown_views(self) -> list[QWidget]:
        """Get the views which are currently shown, in display order."""
        return list(self._shown)

    def add_view(self, view: QWidget) -> None:
        """Take ownership of a view, initially hidden."""
        # Explicitly hide first so QSplitter doesn't show it when adopting it.
        view.hide()
        self.addWidget(view)

    def remove_view(self, view: QWidget) -> None:
        """Stop showing a view which is about to be removed or destroyed.

        The view stays a child of the host (as with QStackedWidget); the caller
        is responsible for destroying it.
        """
        log.webview.debug(f"Removing view {view!r}")
        if view in self._shown:
            self._shown.remove(view)
        view.hide()

    def show_views(
        self,
        views: Sequence[QWidget],
        focus: QWidget | None = None,
    ) -> None:
        """Show exactly the given views (first one left/top), hide all others.

        Args:
            views: Zero, one or two views previously added via add_view.
            focus: If keyboard focus was inside a view which gets hidden, move
                   it to this widget (default: the first view) instead of
                   letting Qt pick the next widget in the focus chain.
        """
        if len(views) > self.MAX_VIEWS:
            raise ValueError(f"Can show at most {self.MAX_VIEWS} views, "
                             f"got {len(views)}")
        if len(set(views)) != len(views):
            raise ValueError("Can't show the same view twice")
        for view in views:
            if self.indexOf(view) == -1:
                raise ValueError(f"{view!r} is not owned by this host")

        log.webview.debug(f"Showing views {list(views)!r}, "
                          f"previously {self._shown!r}")

        old = [view for view in self._shown if view not in views]
        focus_widget = QApplication.focusWidget()
        had_focus = focus_widget is not None and any(
            view is focus_widget or view.isAncestorOf(focus_widget)
            for view in old)

        self._shown = list(views)

        # Order the pair, without reparenting (the widgets already are our
        # children, so QSplitter only moves them within its own list).
        if len(views) == 2 and self.indexOf(views[0]) > self.indexOf(views[1]):
            self.insertWidget(self.indexOf(views[1]), views[0])

        for view in views:
            view.show()

        if had_focus:
            target = focus if focus is not None else (views[0] if views else None)
            if target is not None:
                target.setFocus()

        for view in old:
            view.hide()
