# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Display host for the TabWidget: shows one tab, or the two tabs of a pair.

All tab widgets are permanent children of the host and only their visibility is
toggled (a QSplitter lays out visible children only). They are never
reparented, as that would disturb the web page inside.
"""

import dataclasses
from collections.abc import Sequence

from qutebrowser.qt.core import Qt, pyqtSlot
from qutebrowser.qt.widgets import QApplication, QSplitter, QWidget


@dataclasses.dataclass(eq=False)
class ViewPair:

    """Two views which are shown next to each other.

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
        return view is self.first or view is self.second

    def other(self, view: QWidget) -> QWidget:
        """Get the view which is paired with the given one."""
        assert self.contains(view), view
        return self.second if view is self.first else self.first


class ViewHost(QSplitter):

    """A splitter which owns all tab widgets and shows at most two of them.

    Attributes:
        _pair: The ViewPair currently shown, or None. Dragging the divider
               updates its ratio.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setChildrenCollapsible(False)
        self._pair: ViewPair | None = None
        self.splitterMoved.connect(self._on_splitter_moved)

    def add_view(self, view: QWidget) -> None:
        """Take ownership of a view, initially hidden."""
        # Hide it explicitly first, or QSplitter shows it when adopting it.
        view.hide()
        self.addWidget(view)

    def show_views(
        self,
        views: Sequence[QWidget],
        focus: QWidget | None = None,
    ) -> None:
        """Show exactly the given views (first one left/top), hide all others.

        Args:
            views: At most two views previously added via add_view.
            focus: If keyboard focus is in a view which gets hidden, move it
                   to this widget first. Otherwise Qt picks the next widget
                   in the focus chain, which can be the other half of a pair.
        """
        assert len(views) <= 2, views

        children = [self.widget(i) for i in range(self.count())]
        hidden = [view for view in children
                  if view is not None and view not in views]
        focus_widget = QApplication.focusWidget()
        had_focus = focus_widget is not None and any(
            view is focus_widget or view.isAncestorOf(focus_widget)
            for view in hidden)

        self._pair = None
        # Reorder within the splitter, this doesn't reparent anything.
        if len(views) == 2 and self.indexOf(views[0]) > self.indexOf(views[1]):
            self.insertWidget(self.indexOf(views[1]), views[0])
        for view in views:
            view.show()
        if had_focus and focus is not None:
            focus.setFocus()
        for view in hidden:
            view.hide()

    def show_pair(self, pair: ViewPair, focus: QWidget | None = None) -> None:
        """Show both views of a pair, using its orientation and ratio."""
        self.show_views([pair.first, pair.second], focus=focus)
        self.setOrientation(pair.orientation)
        # Only the proportions matter, QSplitter scales to the available space.
        sizes = [0] * self.count()
        sizes[self.indexOf(pair.first)] = round(pair.ratio * 1000)
        sizes[self.indexOf(pair.second)] = round((1 - pair.ratio) * 1000)
        self.setSizes(sizes)
        self._pair = pair

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
