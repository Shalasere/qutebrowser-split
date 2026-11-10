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


def _laid_out(view):
    return view.isVisible() and view.width() > 50 and view.height() > 50


@pytest.fixture
def show(host, qtbot):
    """Show views, and wait until they are laid out."""
    def _show(*to_show):
        host.show_views(to_show)
        qtbot.wait_until(lambda: all(_laid_out(view) for view in to_show))
    return _show


class TestShowViews:

    def test_added_views_are_hidden(self, views):
        assert not any(view.isVisible() for view in views)

    def test_single_view_fills_host(self, host, views, show):
        show(views[0])
        assert views[0].size() == host.size()
        assert not views[1].isVisible()

    def test_switching_hides_the_previous_view(self, views, show):
        show(views[0])
        show(views[1])
        assert not views[0].isVisible()

    def test_nothing_shown(self, host, views, show):
        show(views[0])
        host.show_views([])
        assert not any(view.isVisible() for view in views)

    def test_pair_follows_argument_order(self, views, show):
        show(views[2], views[0])
        assert views[2].x() < views[0].x()
        assert not views[1].isVisible()

    def test_views_are_never_reparented(self, host, views, show):
        show(views[0], views[2])
        show(views[2], views[0])
        show(views[1])
        assert all(view.parentWidget() is host for view in views)


class TestFocus:

    @pytest.fixture
    def edits(self, host, qtbot):
        result = [QLineEdit() for _ in range(3)]
        for edit in result:
            host.add_view(edit)
        host.show_views([result[0]])
        host.activateWindow()
        result[0].setFocus()
        qtbot.wait_until(lambda: QApplication.focusWidget() is result[0])
        return result

    def test_focus_goes_to_the_requested_view(self, host, edits):
        first, second, third = edits
        host.show_views([second, third], focus=third)
        assert QApplication.focusWidget() is third
        assert not first.isVisible()

    def test_focus_is_left_alone_if_not_in_a_hidden_view(self, host, edits):
        first, second, _third = edits
        host.show_views([first, second], focus=second)
        assert QApplication.focusWidget() is first


class TestViewPair:

    @pytest.mark.parametrize("ratio, expected", [
        (0.3, 0.3),
        (0, viewhost.ViewPair.MIN_RATIO),
        (50, 1 - viewhost.ViewPair.MIN_RATIO),
    ])
    def test_ratio_is_clamped(self, ratio, expected):
        pair = viewhost.ViewPair(QWidget(), QWidget(), ratio=ratio)
        assert pair.ratio == pytest.approx(expected)

    def test_contains_and_other(self):
        first, second, third = QWidget(), QWidget(), QWidget()
        pair = viewhost.ViewPair(first, second)
        assert pair.contains(first)
        assert not pair.contains(third)
        assert not pair.contains(None)
        assert pair.other(first) is second
        assert pair.other(second) is first


class TestShowPair:

    @pytest.fixture
    def show_pair(self, host, qtbot):
        def _show_pair(pair):
            host.show_pair(pair)
            qtbot.wait_until(lambda: _laid_out(pair.first) and
                             _laid_out(pair.second))
        return _show_pair

    def test_orientation_and_ratio(self, views, show_pair):
        pair = viewhost.ViewPair(
            views[0], views[2], Qt.Orientation.Vertical, ratio=0.25)
        show_pair(pair)
        assert views[0].y() < views[2].y()
        total = views[0].height() + views[2].height()
        assert views[0].height() / total == pytest.approx(0.25, abs=0.03)

    def test_dragging_the_divider_updates_the_ratio(
            self, host, views, show, show_pair):
        pair = viewhost.ViewPair(views[0], views[1])
        show_pair(pair)
        host.moveSplitter(300, 1)
        assert pair.ratio == pytest.approx(0.3, abs=0.03)

        show(views[2])
        show_pair(pair)
        total = views[0].width() + views[1].width()
        assert views[0].width() / total == pytest.approx(0.3, abs=0.03)
