# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for mainwindow.viewhost."""

import pytest

from qutebrowser.qt.core import Qt
from qutebrowser.qt.widgets import QWidget, QLineEdit, QApplication

from qutebrowser.mainwindow import viewhost


@pytest.fixture
def host(qtbot):
    h = viewhost.ViewHost()
    qtbot.add_widget(h)
    h.resize(1000, 600)
    h.show()
    qtbot.wait_exposed(h)
    return h


@pytest.fixture
def views(host):
    result = [QWidget() for _ in range(3)]
    for view in result:
        host.add_view(view)
    return result


@pytest.fixture
def show(host, qtbot):
    """Show views, and wait until the splitter laid them out."""
    def _show(to_show, **kwargs):
        host.show_views(to_show, **kwargs)
        qtbot.wait_until(lambda: all(_is_shown(view) for view in to_show),
                         timeout=2000)
    return _show


def _is_shown(view):
    return view.isVisible() and view.width() > 50 and view.height() > 50


class TestShowViews:

    def test_added_views_are_hidden(self, host, views, show):
        assert not any(view.isVisible() for view in views)
        assert host.shown_views() == []

    def test_single_view_fills_host(self, host, views, show):
        show([views[0]])
        assert _is_shown(views[0])
        assert not views[1].isVisible()
        assert views[0].width() == host.width()
        assert host.shown_views() == [views[0]]

    def test_switching_hides_the_previous_view(self, host, views, show):
        show([views[0]])
        show([views[1]])
        assert _is_shown(views[1])
        assert not views[0].isVisible()

    def test_nothing_shown(self, host, views, show):
        show([views[0]])
        host.show_views([])
        assert not any(view.isVisible() for view in views)
        assert host.shown_views() == []

    def test_pair_is_shown_side_by_side(self, host, views, show):
        show([views[0], views[2]])
        assert _is_shown(views[0])
        assert _is_shown(views[2])
        assert not views[1].isVisible()
        assert views[0].x() < views[2].x()
        assert host.shown_views() == [views[0], views[2]]

    def test_pair_order_follows_argument_order(self, host, views, show):
        show([views[2], views[0]])
        assert views[2].x() < views[0].x()

    def test_vertical_orientation(self, host, views, show):
        host.setOrientation(Qt.Orientation.Vertical)
        show([views[0], views[1]])
        assert views[0].y() < views[1].y()
        assert views[0].width() == host.width()

    def test_pair_survives_switching_to_another_view(self, host, views, show):
        show([views[0], views[1]])
        show([views[2]])
        assert _is_shown(views[2])
        assert not views[0].isVisible()
        assert not views[1].isVisible()
        show([views[0], views[1]])
        assert _is_shown(views[0])
        assert _is_shown(views[1])
        assert not views[2].isVisible()

    def test_divider_position_is_kept(self, host, views, show):
        show([views[0], views[1]])
        host.setSizes([300, 700])
        show([views[2]])
        show([views[0], views[1]])
        assert 250 < views[0].width() < 350

    def test_views_are_never_reparented(self, host, views, show):
        identities = [(view, view.parentWidget()) for view in views]
        show([views[0], views[2]])
        show([views[2], views[0]])
        host.setOrientation(Qt.Orientation.Vertical)
        show([views[1]])
        show([views[0], views[1]])
        assert [(view, view.parentWidget()) for view in views] == identities
        assert all(view.parentWidget() is host for view in views)

    def test_too_many_views(self, host, views):
        with pytest.raises(ValueError, match="at most 2"):
            host.show_views(views)

    def test_same_view_twice(self, host, views):
        with pytest.raises(ValueError, match="same view twice"):
            host.show_views([views[0], views[0]])

    def test_foreign_view(self, host, views):
        stranger = QWidget()
        with pytest.raises(ValueError, match="not owned"):
            host.show_views([stranger])
        assert host.shown_views() == []


class TestRemoveView:

    def test_removed_view_is_hidden_and_forgotten(self, host, views):
        host.show_views([views[0], views[1]])
        host.remove_view(views[0])
        assert not views[0].isVisible()
        assert host.shown_views() == [views[1]]

    def test_removed_view_stays_a_child(self, host, views):
        # Like QStackedWidget::removeWidget: destroying it is the caller's job.
        host.remove_view(views[0])
        assert views[0].parentWidget() is host


class TestFocus:

    @pytest.fixture
    def focusable(self, host, qtbot):
        edits = [QLineEdit() for _ in range(3)]
        for edit in edits:
            host.add_view(edit)
        host.show_views([edits[0]])
        host.activateWindow()
        edits[0].setFocus()
        qtbot.wait_until(lambda: QApplication.focusWidget() is edits[0],
                         timeout=2000)
        return edits

    def test_focus_follows_to_the_new_view(self, host, focusable):
        first, second, _third = focusable
        host.show_views([second])
        assert QApplication.focusWidget() is second
        assert not first.isVisible()

    def test_explicit_focus_target(self, host, focusable):
        first, second, third = focusable
        # The focused view gets hidden, focus goes to the requested one,
        # which is not the first of the shown views.
        host.show_views([second, third], focus=third)
        assert QApplication.focusWidget() is third
        assert not first.isVisible()

    def test_focus_is_left_alone_if_not_in_a_hidden_view(self, host, focusable):
        first, second, _third = focusable
        host.show_views([first, second], focus=second)
        assert QApplication.focusWidget() is first


class TestViewPair:

    def test_default_ratio_is_half(self):
        pair = viewhost.ViewPair(QWidget(), QWidget())
        assert pair.ratio == 0.5
        assert pair.orientation == Qt.Orientation.Horizontal

    @pytest.mark.parametrize("ratio, expected", [
        (0.3, 0.3),
        (-1, viewhost.ViewPair.MIN_RATIO),
        (0, viewhost.ViewPair.MIN_RATIO),
        (1, 1 - viewhost.ViewPair.MIN_RATIO),
        (50, 1 - viewhost.ViewPair.MIN_RATIO),
    ])
    def test_ratio_is_clamped(self, ratio, expected):
        pair = viewhost.ViewPair(QWidget(), QWidget(), ratio=ratio)
        assert pair.ratio == pytest.approx(expected)
        pair.set_ratio(ratio)
        assert pair.ratio == pytest.approx(expected)

    def test_contains_and_other(self):
        first, second, third = QWidget(), QWidget(), QWidget()
        pair = viewhost.ViewPair(first, second)
        assert pair.contains(first)
        assert pair.contains(second)
        assert not pair.contains(third)
        assert not pair.contains(None)
        assert pair.other(first) is second
        assert pair.other(second) is first

    def test_pairs_are_compared_by_identity(self):
        first, second = QWidget(), QWidget()
        assert viewhost.ViewPair(first, second) != viewhost.ViewPair(first, second)


class TestShowPair:

    def test_uses_orientation(self, host, views, qtbot):
        pair = viewhost.ViewPair(views[0], views[2], Qt.Orientation.Vertical)
        host.show_pair(pair)
        qtbot.wait_until(lambda: _is_shown(views[0]) and _is_shown(views[2]),
                         timeout=2000)
        assert host.orientation() == Qt.Orientation.Vertical
        assert views[0].y() < views[2].y()
        assert host.shown_views() == [views[0], views[2]]

    def test_ratio_is_applied_to_the_layout(self, host, views, qtbot):
        pair = viewhost.ViewPair(views[0], views[1], ratio=0.25)
        host.show_pair(pair)
        qtbot.wait_until(lambda: views[1].isVisible() and views[1].width() > 50,
                         timeout=2000)
        total = views[0].width() + views[1].width()
        assert views[0].width() / total == pytest.approx(0.25, abs=0.03)

    def test_dragging_the_divider_updates_the_ratio(self, host, views, qtbot):
        pair = viewhost.ViewPair(views[0], views[1])
        host.show_pair(pair)
        qtbot.wait_until(lambda: views[1].isVisible() and views[1].width() > 50,
                         timeout=2000)
        host.moveSplitter(300, 1)
        assert pair.ratio == pytest.approx(0.3, abs=0.03)

    def test_ratio_is_restored_after_showing_something_else(
            self, host, views, qtbot):
        pair = viewhost.ViewPair(views[0], views[1])
        host.show_pair(pair)
        qtbot.wait_until(lambda: views[1].width() > 50, timeout=2000)
        host.moveSplitter(300, 1)
        host.show_views([views[2]])
        assert pair.ratio == pytest.approx(0.3, abs=0.03)  # not touched
        host.show_pair(pair)
        qtbot.wait_until(lambda: views[1].width() > 50, timeout=2000)
        total = views[0].width() + views[1].width()
        assert views[0].width() / total == pytest.approx(0.3, abs=0.03)

    def test_showing_other_views_forgets_the_pair(self, host, views, qtbot):
        pair = viewhost.ViewPair(views[0], views[1])
        host.show_pair(pair)
        host.show_views([views[0], views[1]])
        ratio = pair.ratio
        host.moveSplitter(200, 1)
        assert pair.ratio == ratio
