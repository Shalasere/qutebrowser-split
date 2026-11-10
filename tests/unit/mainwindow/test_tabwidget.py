# SPDX-FileCopyrightText: Daniel Schadt
# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the custom TabWidget/TabBar."""

import functools

import pytest
from unittest.mock import Mock

from qutebrowser.qt.core import Qt
from qutebrowser.qt.gui import QIcon, QPixmap
from qutebrowser.qt.widgets import QApplication
from qutebrowser.mainwindow import tabwidget
from qutebrowser.utils import usertypes


class TestTabWidget:

    """Tests for TabWidget."""

    @pytest.fixture
    def widget(self, qtbot, monkeypatch, config_stub):
        w = tabwidget.TabWidget(0)
        qtbot.add_widget(w)
        monkeypatch.setattr(tabwidget.objects, 'backend',
                            usertypes.Backend.QtWebKit)
        w.show()
        return w

    def test_small_icon_doesnt_crash(self, widget, qtbot, fake_web_tab):
        """Test that setting a small icon doesn't produce a crash.

        Regression test for #1015.
        """
        # Size taken from issue report
        pixmap = QPixmap(72, 1)
        icon = QIcon(pixmap)
        tab = fake_web_tab()
        widget.addTab(tab, icon, 'foobar')

        with qtbot.wait_exposed(widget):
            widget.show()

    # Sizing tests

    def test_tab_size_same(self, widget, fake_web_tab):
        """Ensure by default, all tab sizes are the same."""
        num_tabs = 10
        for i in range(num_tabs):
            widget.addTab(fake_web_tab(), 'foobar' + str(i))

        first_size = widget.tabBar().tabSizeHint(0)
        first_size_min = widget.tabBar().minimumTabSizeHint(0)

        for i in range(num_tabs):
            assert first_size == widget.tabBar().tabSizeHint(i)
            assert first_size_min == widget.tabBar().minimumTabSizeHint(i)

    @pytest.fixture
    def paint_spy(self, monkeypatch):
        spy = Mock()
        monkeypatch.setattr(tabwidget, "QStylePainter", spy)
        return spy

    def test_tab_text_edlided_for_narrow_tabs(self, paint_spy, widget, fake_web_tab):
        """Make sure text gets elided for narrow tabs."""
        widget.setMaximumWidth(100)
        widget.addTab(fake_web_tab(), "one two three four")

        fake_paint_event = Mock()
        fake_paint_event.region.return_value.intersects.return_value = True
        widget.tabBar().paintEvent(fake_paint_event)

        style_opt = paint_spy.return_value.drawControl.call_args_list[0][0][1]
        assert len(style_opt.text) < len(widget.tabBar().tabText(0))
        assert style_opt.text.endswith("…")
        assert len(style_opt.text) > len("…")

    def test_tab_text_not_edlided_for_wide_tabs(self, paint_spy, widget, fake_web_tab):
        """Make sure text doesn't get elided for wide tabs."""
        widget.setMaximumWidth(200)
        widget.addTab(fake_web_tab(), "one two three four")

        fake_paint_event = Mock()
        fake_paint_event.region.return_value.intersects.return_value = True
        widget.tabBar().paintEvent(fake_paint_event)

        style_opt = paint_spy.return_value.drawControl.call_args_list[0][0][1]
        assert style_opt.text.endswith(widget.tabBar().tabText(0))

    @pytest.mark.parametrize("shrink_pinned", [True, False])
    @pytest.mark.parametrize("vertical", [True, False])
    def test_pinned_size(self, widget, fake_web_tab, config_stub,
                         shrink_pinned, vertical):
        """Ensure by default, pinned min sizes are forced to title.

        If pinned.shrink is not true, then all tabs should be the same

        If tabs are vertical, all tabs should be the same"""
        num_tabs = 10
        for i in range(num_tabs):
            widget.addTab(fake_web_tab(), 'foobar' + str(i))

        # Set pinned title format longer than unpinned
        config_stub.val.tabs.title.format_pinned = "_" * 10
        config_stub.val.tabs.title.format = "_" * 2
        config_stub.val.tabs.pinned.shrink = shrink_pinned
        if vertical:
            # Use pixel width so we don't need to mock main-window
            config_stub.val.tabs.width = 50
            config_stub.val.tabs.position = "left"

        pinned_num = [1, num_tabs - 1]
        for num in pinned_num:
            tab = widget.widget(num)
            tab.set_pinned(True)

        first_size = widget.tabBar().tabSizeHint(0)
        first_size_min = widget.tabBar().minimumTabSizeHint(0)

        for i in range(num_tabs):
            if i in pinned_num and shrink_pinned and not vertical:
                assert (first_size.width() >
                        widget.tabBar().tabSizeHint(i).width())
                assert (first_size_min.width() <
                        widget.tabBar().minimumTabSizeHint(i).width())
            else:
                assert first_size == widget.tabBar().tabSizeHint(i)
                assert first_size_min == widget.tabBar().minimumTabSizeHint(i)

    @pytest.mark.parametrize("num_tabs", [4, 10, 50, 100])
    def test_update_tab_titles_benchmark(self, benchmark, widget,
                                         qtbot, fake_web_tab, num_tabs):
        """Benchmark for update_tab_titles."""
        for i in range(num_tabs):
            widget.addTab(fake_web_tab(), 'foobar' + str(i))

        with qtbot.wait_exposed(widget):
            widget.show()

        benchmark(widget.update_tab_titles)

    def test_tab_min_width(self, widget, fake_web_tab, config_stub, qtbot):
        widget.addTab(fake_web_tab(), 'foobar')
        widget.addTab(fake_web_tab(), 'foobar1')
        min_size = widget.tabBar().tabRect(0).width() + 10
        config_stub.val.tabs.min_width = min_size
        assert widget.tabBar().tabRect(0).width() == min_size

    def test_tab_max_width(self, widget, fake_web_tab, config_stub, qtbot):
        widget.addTab(fake_web_tab(), 'foobar')
        max_size = widget.tabBar().tabRect(0).width() - 10
        config_stub.val.tabs.max_width = max_size
        assert widget.tabBar().tabRect(0).width() == max_size

    def test_tab_stays_hidden(self, widget, fake_web_tab, config_stub):
        assert widget.tabBar().isVisible()
        config_stub.val.tabs.show = "never"
        assert not widget.tabBar().isVisible()
        for i in range(12):
            widget.addTab(fake_web_tab(), 'foobar' + str(i))
        assert not widget.tabBar().isVisible()

    @pytest.mark.parametrize("num_tabs", [4, 70])
    @pytest.mark.parametrize("rev", [True, False])
    def test_add_remove_tab_benchmark(self, benchmark, widget,
                                      qtbot, fake_web_tab, num_tabs, rev):
        """Benchmark for addTab and removeTab."""
        def _run_bench():
            with qtbot.wait_exposed(widget):
                widget.show()
            for i in range(num_tabs):
                idx = i if rev else 0
                widget.insertTab(idx, fake_web_tab(), 'foobar' + str(i))

            to_del = range(num_tabs)
            if rev:
                to_del = reversed(to_del)
            for i in to_del:
                widget.removeTab(i)

        benchmark(_run_bench)

    def test_tab_pinned_benchmark(self, benchmark, widget, fake_web_tab):
        """Benchmark for _tab_pinned."""
        widget.addTab(fake_web_tab(), 'foobar')
        tab_bar = widget.tabBar()
        benchmark(functools.partial(tab_bar._tab_pinned, 0))


HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical


@pytest.fixture
def widget(qtbot, monkeypatch, config_stub):
    w = tabwidget.TabWidget(0)
    qtbot.add_widget(w)
    monkeypatch.setattr(tabwidget.objects, 'backend',
                        usertypes.Backend.QtWebKit)
    w.resize(800, 600)
    w.show()
    qtbot.wait_exposed(w)
    return w


@pytest.fixture
def tabs(widget, fake_web_tab):
    result = [fake_web_tab(tab_id=i) for i in range(5)]
    for i, tab in enumerate(result):
        widget.addTab(tab, f'tab{i}')
    return result


def visible(tabs):
    return [i for i, tab in enumerate(tabs) if tab.isVisible()]


class TestTabApi:

    """Tests for the indices and display of tabs, which QTabWidget did."""

    def test_empty(self, widget):
        assert widget.count() == 0
        assert widget.currentIndex() == -1
        assert widget.currentWidget() is None

    def test_insert_move_remove(self, widget, tabs, fake_web_tab):
        new = fake_web_tab()
        assert widget.insertTab(1, new, 'new') == 1
        assert widget.currentWidget() is tabs[0]

        widget.setCurrentWidget(tabs[2])
        widget.tabBar().moveTab(0, 3)
        widget.removeTab(widget.indexOf(tabs[4]))

        order = [new, tabs[1], tabs[2], tabs[0], tabs[3]]
        assert [widget.widget(i) for i in range(5)] == order
        assert [widget.indexOf(tab) for tab in order] == list(range(5))
        assert widget.indexOf(tabs[4]) == -1
        assert widget.currentWidget() is tabs[2]
        assert all(tab.parentWidget() is widget._view_host for tab in order)

    @pytest.mark.parametrize('idx', [-1, 99])
    def test_insert_out_of_range_appends(self, widget, tabs, fake_web_tab, idx):
        assert widget.insertTab(idx, fake_web_tab(), 'new') == 5

    def test_only_current_tab_is_shown(self, widget, tabs):
        assert visible(tabs) == [0]
        widget.setCurrentIndex(3)
        assert visible(tabs) == [3]
        widget.removeTab(3)
        assert len(visible(tabs)) == 1
        for _ in range(4):
            widget.removeTab(0)
        assert widget.currentWidget() is None
        assert visible(tabs) == []

    def test_signal_order(self, widget, tabs):
        """currentChanged (TabbedBrowser) comes before tab_index_changed."""
        seen = []
        widget.currentChanged.connect(
            lambda idx: seen.append(('current', visible(tabs))))
        widget.tab_index_changed.connect(
            lambda idx, count: seen.append(('index', visible(tabs))))
        widget.setCurrentIndex(2)
        assert seen == [('current', [2]), ('index', [2])]

    @pytest.mark.parametrize('position, check', [
        ('top', lambda bar, host: bar.geometry().bottom() <= host.y()),
        ('bottom', lambda bar, host: host.geometry().bottom() <= bar.y()),
        ('left', lambda bar, host: bar.geometry().right() <= host.x()),
        ('right', lambda bar, host: host.geometry().right() <= bar.x()),
    ])
    def test_tab_position(self, widget, tabs, config_stub, qtbot,
                          position, check):
        config_stub.val.tabs.width = 50  # pixels, so we don't need main-window
        config_stub.val.tabs.position = position
        bar = widget.tabBar()
        qtbot.wait_until(lambda: check(bar, widget._view_host))
        assert bar.vertical == (position in ['left', 'right'])
        qtbot.wait_until(lambda: tabs[0].size() == widget._view_host.size())


class TestPairs:

    def test_pair_is_shown_together(self, widget, tabs, qtbot):
        pair = widget.pair_tabs(tabs[0], tabs[2], HORIZONTAL)
        qtbot.wait_until(lambda: tabs[2].width() > 50)
        assert visible(tabs) == [0, 2]
        assert tabs[0].x() < tabs[2].x()
        assert widget.pairs() == [pair]
        assert widget.pair_of(tabs[2]) is pair
        assert widget.pair_of(tabs[1]) is None

        widget.setCurrentWidget(tabs[2])
        assert visible(tabs) == [0, 2]

        widget.setCurrentWidget(tabs[3])
        assert visible(tabs) == [3]
        widget.setCurrentWidget(tabs[0])
        assert visible(tabs) == [0, 2]

    def test_ratio_is_kept(self, widget, tabs, qtbot):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        qtbot.wait_until(lambda: tabs[1].width() > 50)
        widget._view_host.moveSplitter(200, 1)
        widget.setCurrentWidget(tabs[3])
        widget.setCurrentWidget(tabs[0])
        qtbot.wait_until(lambda: tabs[1].width() > 50)
        total = tabs[0].width() + tabs[1].width()
        assert tabs[0].width() / total == pytest.approx(0.25, abs=0.03)

    def test_pairing_again_changes_the_orientation(self, widget, tabs, qtbot):
        pair = widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.setCurrentWidget(tabs[1])
        assert widget.pair_tabs(tabs[1], tabs[0], VERTICAL) is pair
        assert (pair.first, pair.second) == (tabs[0], tabs[1])
        qtbot.wait_until(lambda: tabs[1].width() > 50)
        assert tabs[0].y() < tabs[1].y()
        assert widget.pairs() == [pair]

    def test_two_pairs(self, widget, tabs):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.pair_tabs(tabs[2], tabs[3], VERTICAL)
        widget.setCurrentWidget(tabs[3])
        assert visible(tabs) == [2, 3]
        widget.setCurrentWidget(tabs[1])
        assert visible(tabs) == [0, 1]

    @pytest.mark.parametrize('first, second, pinned, message', [
        (0, 0, None, "with itself"),
        (0, 2, 0, "pinned"),
        (0, 2, 2, "pinned"),
        (0, 2, None, "already part of a split"),
        (2, 1, None, "already part of a split"),
    ])
    def test_cant_pair(self, widget, tabs, first, second, pinned, message):
        pair = widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        if pinned is not None:
            widget.unpair(tabs[0])
            tabs[pinned].set_pinned(True)
            pair = None
        with pytest.raises(ValueError, match=message):
            widget.pair_tabs(tabs[first], tabs[second], HORIZONTAL)
        assert widget.pairs() == ([pair] if pair else [])

    def test_unpair(self, widget, tabs):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        assert widget.unpair(tabs[1])
        assert not widget.unpair(tabs[1])
        assert visible(tabs) == [0]
        assert widget.count() == 5

    @pytest.mark.parametrize('closed, current', [
        (0, 0), (0, 1), (1, 0), (1, 1),
    ])
    def test_closing_a_member_dissolves_the_pair(
            self, widget, tabs, closed, current):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.setCurrentWidget(tabs[current])
        widget.removeTab(closed)
        assert widget.pairs() == []
        assert len(visible(tabs)) == 1

    @pytest.mark.parametrize('src, dest, dissolves', [
        (0, 3, True), (1, 0, True), (3, 0, False),
    ])
    def test_moving_a_tab(self, widget, tabs, src, dest, dissolves):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.tabBar().moveTab(src, dest)
        assert bool(widget.pairs()) != dissolves
        assert len(visible(tabs)) == (1 if dissolves else 2)

    def test_closing_another_tab_keeps_the_pair(self, widget, tabs):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.removeTab(3)
        assert visible(tabs) == [0, 1]

    def test_new_tabs(self, widget, tabs, fake_web_tab):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.insertTab(1, fake_web_tab(), 'background')
        assert visible(tabs) == [0, 1]
        new = fake_web_tab()
        widget.setCurrentIndex(widget.insertTab(6, new, 'foreground'))
        assert visible(tabs) == []
        assert new.isVisible()
        assert len(widget.pairs()) == 1

    def test_full_screen_shows_only_that_page(self, widget, tabs, qtbot):
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        tabs[0].data.fullscreen = True
        widget.update_display()
        assert visible(tabs) == [0]
        tabs[0].data.fullscreen = False
        widget.update_display()
        assert visible(tabs) == [0, 1]


class TestPairFocus:

    """Focus moving into the other half of a pair selects that tab."""

    @pytest.fixture
    def focus_targets(self, widget, tabs, qtbot):
        # Like in a real tab, the focus ends up in a widget inside the tab.
        targets = []
        for tab in tabs:
            target = tab
            while target.focusProxy() is not None:
                target = target.focusProxy()
            target.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            targets.append(target)
        widget.pair_tabs(tabs[0], tabs[1], HORIZONTAL)
        widget.activateWindow()
        targets[0].setFocus()
        qtbot.wait_until(lambda: QApplication.focusWidget() is targets[0])
        return targets

    def test_focusing_the_other_half_selects_it(
            self, widget, tabs, focus_targets):
        focus_targets[1].setFocus()
        assert widget.currentWidget() is tabs[1]
        assert visible(tabs) == [0, 1]

    @pytest.mark.parametrize('idx', [0, 2])
    def test_other_tabs_dont_select(self, widget, tabs, focus_targets, idx):
        focus_targets[idx].setFocus()
        assert widget.currentWidget() is tabs[0]

    @pytest.mark.parametrize('current', [0, 1])
    def test_selecting_a_pair_keeps_the_selection(
            self, widget, tabs, focus_targets, current):
        widget.setCurrentWidget(tabs[3])
        focus_targets[3].setFocus()
        widget.setCurrentWidget(tabs[current])
        assert widget.currentWidget() is tabs[current]

    def test_hidden_other_half_doesnt_select(
            self, widget, tabs, focus_targets):
        tabs[0].data.fullscreen = True
        widget.update_display()
        focus_targets[1].setFocus()
        assert widget.currentWidget() is tabs[0]

    def test_without_pair(self, widget, tabs, focus_targets):
        widget.unpair(tabs[0])
        focus_targets[1].setFocus()
        assert widget.currentWidget() is tabs[0]
