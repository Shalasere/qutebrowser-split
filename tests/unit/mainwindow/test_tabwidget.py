# SPDX-FileCopyrightText: Daniel Schadt
# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the custom TabWidget/TabBar."""

import functools

import pytest
from unittest.mock import Mock

from qutebrowser.qt.gui import QIcon, QPixmap
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
