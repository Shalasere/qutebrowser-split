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

import dataclasses
from collections.abc import Sequence

from qutebrowser.qt.core import Qt, pyqtSlot
from qutebrowser.qt.widgets import QApplication, QSplitter, QWidget

from qutebrowser.utils import log


@dataclasses.dataclass(eq=False)
class ViewPair:

    """Two views which are shown next to each other.

    Compared by identity, so every pair is a distinct object even if it
    describes the same views.

    Attributes:
        first: The view shown on the left/top.
        second: The view shown on the right/bottom.
        orientation: Qt.Orientation.Horizontal for left/right,
                     Qt.Orientation.Vertical for top/bottom.
        ratio: The fraction of the space given to the first view, always
               between MIN_RATIO and 1 - MIN_RATIO.

    Class attributes:
        MIN_RATIO: The smallest fraction of the space a view can get.
    """

    MIN_RATIO = 0.1

    first: QWidget
    second: QWidget
    orientation: Qt.Orientation = Qt.Orientation.Horizontal
    ratio: float = 0.5

    def __post_init__(self) -> None:
        self.set_ratio(self.ratio)

    def set_ratio(self, ratio: float) -> None:
        """Set the ratio, clamped so neither view can disappear."""
        self.ratio = min(max(ratio, self.MIN_RATIO), 1 - self.MIN_RATIO)

    def contains(self, view: QWidget | None) -> bool:
        """Check whether the given view is part of this pair."""
        return view is not None and (view is self.first or view is self.second)

    def other(self, view: QWidget) -> QWidget:
        """Get the view which is paired with the given one."""
        assert self.contains(view), view
        return self.second if view is self.first else self.first


class ViewHost(QSplitter):

    """A splitter which owns all tab widgets and shows at most two of them.

    Attributes:
        _shown: The views currently shown, in display order.
        _pair: The ViewPair currently shown, or None. Dragging the divider
               updates its ratio.

    Class attributes:
        MAX_VIEWS: How many views can be shown at the same time.
    """

    MAX_VIEWS = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setChildrenCollapsible(False)
        self._shown: list[QWidget] = []
        self._pair: ViewPair | None = None
        self.splitterMoved.connect(self._on_splitter_moved)

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
        self._pair = None

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

    def show_pair(self, pair: ViewPair, focus: QWidget | None = None) -> None:
        """Show both views of a pair, using its orientation and ratio."""
        self.show_views([pair.first, pair.second], focus=focus)
        self.setOrientation(pair.orientation)
        # The sizes are only relative to each other, QSplitter scales them to
        # the space available.
        self.setSizes(self._sizes_for(pair))
        self._pair = pair

    def _sizes_for(self, pair: ViewPair) -> list[int]:
        """Get a QSplitter sizes list which shows the given pair."""
        sizes = [0] * self.count()
        sizes[self.indexOf(pair.first)] = round(pair.ratio * 1000)
        sizes[self.indexOf(pair.second)] = round((1 - pair.ratio) * 1000)
        return sizes

    @pyqtSlot()
    def _on_splitter_moved(self) -> None:
        """Remember where the user put the divider."""
        if self._pair is None:
            return
        sizes = self.sizes()
        first = sizes[self.indexOf(self._pair.first)]
        second = sizes[self.indexOf(self._pair.second)]
        if first + second > 0:
            self._pair.set_ratio(first / (first + second))
