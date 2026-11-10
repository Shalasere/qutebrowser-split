# SPDX-FileCopyrightText: Daniel Schadt
# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the custom TabWidget/TabBar."""

import types
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


class TestTabApi:

    """Tests for the QTabWidget-compatible tab API of TabWidget.

    The tab widgets are owned and displayed by the TabWidget's ViewHost, so
    the index <-> tab mapping is done by TabWidget and has to stay correct
    when tabs are inserted, moved and removed.
    """

    @pytest.fixture
    def widget(self, qtbot, monkeypatch, config_stub):
        w = tabwidget.TabWidget(0)
        qtbot.add_widget(w)
        monkeypatch.setattr(tabwidget.objects, 'backend',
                            usertypes.Backend.QtWebKit)
        w.resize(800, 600)
        w.show()
        qtbot.wait_exposed(w)
        return w

    @pytest.fixture
    def tabs(self, widget, fake_web_tab):
        result = [fake_web_tab(tab_id=i) for i in range(4)]
        for i, tab in enumerate(result):
            widget.addTab(tab, f'tab{i}')
        return result

    def test_empty(self, widget):
        assert widget.count() == 0
        assert widget.currentIndex() == -1
        assert widget.currentWidget() is None
        assert widget.widget(0) is None

    def test_add_tab_returns_index(self, widget, fake_web_tab):
        assert widget.addTab(fake_web_tab(), 'one') == 0
        assert widget.addTab(fake_web_tab(), 'two') == 1

    def test_mapping(self, widget, tabs):
        assert widget.count() == 4
        for i, tab in enumerate(tabs):
            assert widget.widget(i) is tab
            assert widget.indexOf(tab) == i

    @pytest.mark.parametrize('idx', [-1, 4, 100])
    def test_widget_out_of_range(self, widget, tabs, idx):
        assert widget.widget(idx) is None

    def test_index_of_unknown_widget(self, widget, tabs, fake_web_tab):
        assert widget.indexOf(fake_web_tab()) == -1
        assert widget.indexOf(None) == -1

    def test_first_tab_becomes_current(self, widget, tabs):
        assert widget.currentIndex() == 0
        assert widget.currentWidget() is tabs[0]

    def test_insert_in_the_middle(self, widget, tabs, fake_web_tab):
        new = fake_web_tab()
        assert widget.insertTab(1, new, 'new') == 1
        order = [tabs[0], new, tabs[1], tabs[2], tabs[3]]
        assert [widget.widget(i) for i in range(5)] == order
        assert [widget.indexOf(tab) for tab in order] == list(range(5))

    @pytest.mark.parametrize('idx', [-1, 99])
    def test_insert_out_of_range_appends(self, widget, tabs, fake_web_tab, idx):
        new = fake_web_tab()
        assert widget.insertTab(idx, new, 'new') == 4
        assert widget.widget(4) is new

    def test_insert_before_current_keeps_current_tab(self, widget, tabs,
                                                     fake_web_tab):
        widget.setCurrentIndex(2)
        widget.insertTab(0, fake_web_tab(), 'new')
        assert widget.currentIndex() == 3
        assert widget.currentWidget() is tabs[2]
        assert tabs[2].isVisible()

    def test_insert_with_icon(self, widget, fake_web_tab):
        pixmap = QPixmap(16, 16)
        pixmap.fill()
        tab = fake_web_tab()
        widget.insertTab(0, tab, QIcon(pixmap), 'with icon')
        assert not widget.tabBar().tabIcon(0).isNull()
        assert widget.page_title(0) == 'with icon'

    def test_tab_move_keeps_mapping(self, widget, tabs):
        widget.tabBar().moveTab(0, 2)
        order = [tabs[1], tabs[2], tabs[0], tabs[3]]
        assert [widget.widget(i) for i in range(4)] == order
        assert [widget.indexOf(tab) for tab in order] == list(range(4))

    def test_current_tab_follows_a_move(self, widget, tabs):
        widget.setCurrentIndex(0)
        widget.tabBar().moveTab(0, 3)
        assert widget.currentIndex() == 3
        assert widget.currentWidget() is tabs[0]
        assert tabs[0].isVisible()

    def test_set_current_widget(self, widget, tabs):
        widget.setCurrentWidget(tabs[2])
        assert widget.currentIndex() == 2

    def test_only_current_tab_is_visible(self, widget, tabs, qtbot):
        widget.setCurrentIndex(1)
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        assert [tab.isVisible() for tab in tabs] == [False, True, False, False]
        widget.setCurrentIndex(3)
        qtbot.wait_until(lambda: tabs[3].width() > 50, timeout=2000)
        assert [tab.isVisible() for tab in tabs] == [False, False, False, True]

    def test_tab_fills_available_space(self, widget, tabs, qtbot):
        qtbot.wait_until(lambda: tabs[0].width() > 50, timeout=2000)
        assert tabs[0].width() == widget.width()
        assert tabs[0].height() == widget.height() - widget.tabBar().height()

    def test_tabs_are_never_reparented(self, widget, tabs, fake_web_tab):
        widget.setCurrentIndex(2)
        widget.tabBar().moveTab(0, 3)
        widget.insertTab(0, fake_web_tab(), 'new')
        assert all(widget.view_host is tab.parentWidget() for tab in tabs)

    def test_remove_tab(self, widget, tabs):
        widget.removeTab(1)
        assert widget.count() == 3
        assert [widget.widget(i) for i in range(3)] == [
            tabs[0], tabs[2], tabs[3]]
        assert widget.indexOf(tabs[1]) == -1
        assert not tabs[1].isVisible()
        # Like QTabWidget, we don't destroy or reparent it
        assert tabs[1].parentWidget() is widget.view_host

    def test_remove_invalid_index(self, widget, tabs):
        widget.removeTab(99)
        widget.removeTab(-1)
        assert widget.count() == 4

    def test_remove_current_tab_shows_another(self, widget, tabs, qtbot):
        widget.setCurrentIndex(1)
        widget.removeTab(1)
        current = widget.currentWidget()
        assert current is not None
        assert current is not tabs[1]
        qtbot.wait_until(lambda: current.width() > 50, timeout=2000)
        assert [tab.isVisible() for tab in tabs if tab is not tabs[1]
                ] == [tab is current for tab in tabs if tab is not tabs[1]]

    def test_remove_tab_before_current_keeps_current_tab(self, widget, tabs):
        widget.setCurrentIndex(3)
        widget.removeTab(0)
        assert widget.currentIndex() == 2
        assert widget.currentWidget() is tabs[3]
        assert tabs[3].isVisible()

    def test_remove_all_tabs(self, widget, tabs):
        for _ in range(4):
            widget.removeTab(0)
        assert widget.count() == 0
        assert widget.currentWidget() is None
        assert not any(tab.isVisible() for tab in tabs)

    def test_current_changed_is_emitted_after_the_tab_is_shown(
            self, widget, tabs):
        """TabbedBrowser focuses the new tab in a currentChanged slot."""
        seen = []

        def on_changed(idx):
            seen.append((idx, tabs[idx].isVisible(), tabs[0].isVisible()))

        widget.currentChanged.connect(on_changed)
        widget.setCurrentIndex(2)
        assert seen == [(2, True, False)]

    def test_signal_order_matches_qtabwidget(self, widget, tabs):
        """currentChanged (TabbedBrowser) comes before tab_index_changed."""
        order = []
        widget.currentChanged.connect(lambda _idx: order.append('current'))
        widget.tab_index_changed.connect(
            lambda _idx, _count: order.append('index'))
        widget.setCurrentIndex(1)
        assert order == ['current', 'index']

    def test_tab_close_requested_is_forwarded(self, widget, tabs, qtbot):
        with qtbot.wait_signal(widget.tabCloseRequested) as blocker:
            widget.tabBar().tabCloseRequested.emit(2)
        assert blocker.args == [2]

    @pytest.mark.parametrize('position, check', [
        ('top', lambda bar, host: bar.geometry().bottom() <= host.y()),
        ('bottom', lambda bar, host: host.geometry().bottom() <= bar.y()),
        ('left', lambda bar, host: bar.geometry().right() <= host.x()),
        ('right', lambda bar, host: host.geometry().right() <= bar.x()),
    ])
    def test_tab_position(self, widget, tabs, config_stub, qtbot,
                          position, check):
        # Use pixel width so we don't need to mock main-window
        config_stub.val.tabs.width = 50
        config_stub.val.tabs.position = position
        bar = widget.tabBar()
        qtbot.wait_until(lambda: check(bar, widget.view_host), timeout=2000)
        assert bar.vertical == (position in ['left', 'right'])
        # The displayed tab still fills the host.
        qtbot.wait_until(
            lambda: tabs[0].size() == widget.view_host.size(), timeout=2000)


class TestPairs:

    """Tests for pairing tabs of a TabWidget."""

    HORIZONTAL = Qt.Orientation.Horizontal
    VERTICAL = Qt.Orientation.Vertical

    @pytest.fixture
    def widget(self, qtbot, monkeypatch, config_stub):
        w = tabwidget.TabWidget(0)
        qtbot.add_widget(w)
        monkeypatch.setattr(tabwidget.objects, 'backend',
                            usertypes.Backend.QtWebKit)
        w.resize(800, 600)
        w.show()
        qtbot.wait_exposed(w)
        return w

    @pytest.fixture
    def tabs(self, widget, fake_web_tab):
        result = [fake_web_tab(tab_id=i) for i in range(5)]
        for i, tab in enumerate(result):
            widget.addTab(tab, f'tab{i}')
        return result

    @pytest.fixture
    def visible(self, widget, tabs):
        """Get the indices of the visible tabs, after the layout settled."""
        def _visible():
            return [i for i, tab in enumerate(tabs) if tab.isVisible()]
        return _visible

    @pytest.fixture
    def pair01(self, widget, tabs):
        """Pair tab 0 with tab 1, tab 0 being current."""
        return widget.pair_tabs(tabs[0], tabs[1], self.HORIZONTAL)

    def test_no_pairs_initially(self, widget, tabs):
        assert widget.pairs() == []
        assert widget.pair_of(tabs[0]) is None
        assert widget.pair_of(None) is None

    def test_pairing_shows_both_tabs(self, widget, tabs, visible, qtbot):
        pair = widget.pair_tabs(tabs[0], tabs[2], self.HORIZONTAL)
        qtbot.wait_until(lambda: tabs[2].width() > 50, timeout=2000)
        assert visible() == [0, 2]
        assert widget.pairs() == [pair]
        assert widget.pair_of(tabs[0]) is pair
        assert widget.pair_of(tabs[2]) is pair
        assert widget.pair_of(tabs[1]) is None
        assert tabs[0].x() < tabs[2].x()

    def test_pairing_does_not_change_tabs(self, widget, tabs, pair01):
        assert widget.count() == 5
        assert [widget.widget(i) for i in range(5)] == tabs
        assert widget.currentWidget() is tabs[0]
        assert all(widget.view_host is tab.parentWidget() for tab in tabs)

    def test_selecting_the_partner_keeps_both_visible(
            self, widget, tabs, pair01, visible):
        widget.setCurrentWidget(tabs[1])
        assert widget.currentWidget() is tabs[1]
        assert visible() == [0, 1]
        widget.setCurrentWidget(tabs[0])
        assert visible() == [0, 1]

    def test_unrelated_tab_is_shown_alone_and_pair_returns(
            self, widget, tabs, pair01, visible, qtbot):
        widget.setCurrentWidget(tabs[3])
        assert visible() == [3]
        widget.setCurrentWidget(tabs[1])
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        assert visible() == [0, 1]
        assert widget.pair_of(tabs[0]) is pair01

    def test_divider_ratio_survives_unrelated_tab(
            self, widget, tabs, pair01, qtbot):
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        widget.view_host.moveSplitter(200, 1)
        widget.setCurrentWidget(tabs[3])
        widget.setCurrentWidget(tabs[0])
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        total = tabs[0].width() + tabs[1].width()
        assert tabs[0].width() / total == pytest.approx(0.25, abs=0.03)

    def test_repeating_changes_only_the_orientation(
            self, widget, tabs, pair01, qtbot):
        again = widget.pair_tabs(tabs[0], tabs[1], self.VERTICAL)
        assert again is pair01
        assert widget.pairs() == [pair01]
        assert pair01.orientation == self.VERTICAL
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        assert tabs[0].y() < tabs[1].y()

    def test_repeating_from_the_other_side(self, widget, tabs, pair01):
        widget.setCurrentWidget(tabs[1])
        again = widget.pair_tabs(tabs[1], tabs[0], self.VERTICAL)
        assert again is pair01
        # The order of an existing pair is kept.
        assert (again.first, again.second) == (tabs[0], tabs[1])

    def test_two_independent_pairs(self, widget, tabs, pair01, visible):
        other = widget.pair_tabs(tabs[2], tabs[3], self.VERTICAL)
        assert widget.pairs() == [pair01, other]
        widget.setCurrentWidget(tabs[3])
        assert visible() == [2, 3]
        widget.setCurrentWidget(tabs[1])
        assert visible() == [0, 1]

    def test_pair_with_itself(self, widget, tabs):
        with pytest.raises(ValueError, match="with itself"):
            widget.pair_tabs(tabs[0], tabs[0], self.HORIZONTAL)
        assert widget.pairs() == []

    def test_pair_member_of_another_pair(self, widget, tabs, pair01):
        with pytest.raises(ValueError, match="already part of a split"):
            widget.pair_tabs(tabs[0], tabs[2], self.HORIZONTAL)
        with pytest.raises(ValueError, match="already part of a split"):
            widget.pair_tabs(tabs[2], tabs[1], self.HORIZONTAL)
        assert widget.pairs() == [pair01]

    @pytest.mark.parametrize("pinned_idx", [0, 2])
    def test_pair_pinned_tab(self, widget, tabs, pinned_idx):
        tabs[pinned_idx].set_pinned(True)
        with pytest.raises(ValueError, match="pinned"):
            widget.pair_tabs(tabs[0], tabs[2], self.HORIZONTAL)
        assert widget.pairs() == []

    def test_pair_foreign_tab(self, widget, tabs, fake_web_tab):
        with pytest.raises(ValueError, match="not in this window"):
            widget.pair_tabs(tabs[0], fake_web_tab(), self.HORIZONTAL)

    def test_unpair(self, widget, tabs, pair01, visible):
        assert widget.unpair(tabs[1])
        assert widget.pairs() == []
        assert widget.currentWidget() is tabs[0]
        assert visible() == [0]
        assert widget.count() == 5

    def test_unpair_without_pair(self, widget, tabs, pair01):
        assert not widget.unpair(tabs[3])
        assert widget.pairs() == [pair01]

    @pytest.mark.parametrize("closed, current", [
        (0, 0), (0, 1), (1, 0), (1, 1),
    ])
    def test_removing_a_member_dissolves_the_pair(
            self, widget, tabs, pair01, visible, closed, current):
        widget.setCurrentWidget(tabs[current])
        widget.removeTab(closed)
        assert widget.pairs() == []
        survivor = tabs[1 - closed]
        assert widget.indexOf(survivor) != -1
        # Whichever tab is shown now, it is shown alone.
        assert len(visible()) == 1
        assert not tabs[closed].isVisible()

    def test_removing_the_other_tab_keeps_the_pair(
            self, widget, tabs, pair01, visible):
        widget.removeTab(3)
        assert widget.pairs() == [pair01]
        assert visible() == [0, 1]

    def test_new_background_tab_keeps_the_pair(
            self, widget, tabs, pair01, fake_web_tab):
        new = fake_web_tab()
        widget.insertTab(1, new, 'bg')
        assert widget.pairs() == [pair01]
        assert not new.isVisible()
        assert tabs[0].isVisible()
        assert tabs[1].isVisible()

    def test_new_foreground_tab_is_shown_alone(
            self, widget, tabs, pair01, fake_web_tab):
        new = fake_web_tab()
        idx = widget.insertTab(5, new, 'fg')
        widget.setCurrentIndex(idx)
        assert new.isVisible()
        assert not tabs[0].isVisible()
        assert not tabs[1].isVisible()
        assert widget.pairs() == [pair01]

    @pytest.mark.parametrize("src, dest", [(0, 3), (1, 4), (1, 0)])
    def test_moving_a_member_dissolves_the_pair(
            self, widget, tabs, pair01, visible, src, dest):
        widget.tabBar().moveTab(src, dest)
        assert widget.pairs() == []
        assert len(visible()) == 1

    def test_moving_another_tab_keeps_the_pair(
            self, widget, tabs, pair01, visible):
        widget.tabBar().moveTab(3, 0)
        assert widget.pairs() == [pair01]
        assert len(visible()) == 2

    def test_full_screen_shows_only_that_page(
            self, widget, tabs, pair01, visible, qtbot):
        tabs[0].data.fullscreen = True
        widget.update_display()
        assert visible() == [0]
        tabs[0].data.fullscreen = False
        widget.update_display()
        qtbot.wait_until(lambda: tabs[1].width() > 50, timeout=2000)
        assert visible() == [0, 1]
        assert widget.pairs() == [pair01]

    def test_pairs_returns_a_copy(self, widget, tabs, pair01):
        widget.pairs().clear()
        assert widget.pairs() == [pair01]


class TestPairFocus:

    """Focus moving into the other half of a pair selects that tab."""

    @pytest.fixture
    def env(self, qtbot, monkeypatch, config_stub, fake_web_tab):
        w = tabwidget.TabWidget(0)
        qtbot.add_widget(w)
        monkeypatch.setattr(tabwidget.objects, 'backend',
                            usertypes.Backend.QtWebKit)
        w.resize(800, 600)
        tabs = [fake_web_tab(tab_id=i) for i in range(3)]
        targets = []
        for i, tab in enumerate(tabs):
            # Like a real tab, the focus ends up in a widget inside the tab.
            target = tab
            while target.focusProxy() is not None:
                target = target.focusProxy()
            target.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            targets.append(target)
            w.addTab(tab, f'tab{i}')
        w.pair_tabs(tabs[0], tabs[1], Qt.Orientation.Horizontal)
        w.show()
        qtbot.wait_exposed(w)
        w.activateWindow()
        targets[0].setFocus()
        qtbot.wait_until(lambda: QApplication.focusWidget() is targets[0],
                         timeout=2000)
        return types.SimpleNamespace(widget=w, tabs=tabs, targets=targets)

    def test_focusing_the_other_half_selects_it(self, env, qtbot):
        env.targets[1].setFocus()
        qtbot.wait_until(lambda: env.widget.currentWidget() is env.tabs[1],
                         timeout=2000)
        assert env.tabs[0].isVisible()
        assert env.tabs[1].isVisible()

    def test_focusing_the_current_half_changes_nothing(self, env):
        env.targets[0].setFocus()
        assert env.widget.currentWidget() is env.tabs[0]

    def test_focusing_a_hidden_tab_changes_nothing(self, env):
        env.targets[2].setFocus()
        assert env.widget.currentWidget() is env.tabs[0]

    def test_without_pair(self, env):
        env.widget.unpair(env.tabs[0])
        env.targets[1].setFocus()
        assert env.widget.currentWidget() is env.tabs[0]
