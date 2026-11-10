# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for browser.signalfilter."""

import logging
import dataclasses

import pytest
from qutebrowser.qt.core import pyqtSignal, pyqtSlot, QObject

from qutebrowser.browser import signalfilter


class Signaller(QObject):

    signal = pyqtSignal(str)
    link_hovered = pyqtSignal(str)

    filtered_signal = pyqtSignal(str)
    cur_link_hovered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filtered_signal_arg = None
        self.filtered_signal.connect(self.filtered_signal_slot)

    @pyqtSlot(str)
    def filtered_signal_slot(self, s):
        self.filtered_signal_arg = s


@dataclasses.dataclass
class Objects:

    signal_filter: signalfilter.SignalFilter
    signaller: Signaller


@pytest.fixture
def tab(fake_web_tab):
    return fake_web_tab()


@pytest.fixture
def objects(tab):
    signal_filter = signalfilter.SignalFilter(0)
    signaller = Signaller()
    signaller.signal.connect(
        signal_filter.create(signaller.filtered_signal, tab))
    signaller.link_hovered.connect(
        signal_filter.create(signaller.cur_link_hovered, tab))
    return Objects(signal_filter=signal_filter, signaller=signaller)


@pytest.mark.parametrize('index_of, emitted', [(0, True), (1, False)])
def test_filtering(objects, tabbed_browser_stubs, index_of, emitted):
    browser = tabbed_browser_stubs[0]
    browser.widget.current_index = 0
    browser.widget.index_of = index_of
    objects.signaller.signal.emit('foo')
    if emitted:
        assert objects.signaller.filtered_signal_arg == 'foo'
    else:
        assert objects.signaller.filtered_signal_arg is None


@pytest.mark.parametrize('index_of, verb', [(0, 'emitting'), (1, 'ignoring')])
def test_logging(caplog, objects, tabbed_browser_stubs, index_of, verb):
    browser = tabbed_browser_stubs[0]
    browser.widget.current_index = 0
    browser.widget.index_of = index_of

    with caplog.at_level(logging.DEBUG, logger='signals'):
        objects.signaller.signal.emit('foo')

    expected_msg = "{}: filtered_signal('foo') (tab {})".format(verb, index_of)
    assert caplog.messages == [expected_msg]


@pytest.mark.parametrize('index_of', [0, 1])
def test_no_logging(caplog, objects, tabbed_browser_stubs, index_of):
    browser = tabbed_browser_stubs[0]
    browser.widget.current_index = 0
    browser.widget.index_of = index_of

    with caplog.at_level(logging.DEBUG, logger='signals'):
        objects.signaller.link_hovered.emit('foo')

    assert not caplog.records


def test_runtime_error(objects, tabbed_browser_stubs):
    """Test that there's no crash if indexOf() raises RuntimeError."""
    browser = tabbed_browser_stubs[0]
    browser.widget.current_index = 0
    browser.widget.index_of = RuntimeError
    objects.signaller.signal.emit('foo')
    assert objects.signaller.filtered_signal_arg is None


class TestPane:

    """Tests for tabs which have a split pane (another tab, not in the bar)."""

    @pytest.fixture
    def pane(self, tab, fake_web_tab):
        pane = fake_web_tab()
        pane.data.pane_owner = tab
        tab.data.pane = pane
        return pane

    def _emit(self, signal_filter, tab):
        signaller = Signaller()
        signaller.signal.connect(
            signal_filter.create(signaller.filtered_signal, tab))
        signaller.signal.emit('foo')
        return signaller.filtered_signal_arg

    @pytest.mark.parametrize('pane_active, emitted', [
        (False, True),
        (True, False),
    ])
    def test_page_signals(self, tab, pane, tabbed_browser_stubs,
                          pane_active, emitted):
        """The page is only shown if the pane doesn't have focus."""
        browser = tabbed_browser_stubs[0]
        browser.widget.current_index = 0
        browser.widget.index_of = 0
        tab.data.pane_active = pane_active
        arg = self._emit(signalfilter.SignalFilter(0), tab)
        assert arg == ('foo' if emitted else None)

    @pytest.mark.parametrize('pane_active, emitted', [
        (False, False),
        (True, True),
    ])
    def test_pane_signals(self, tab, pane, tabbed_browser_stubs,
                          pane_active, emitted):
        """The pane is only shown if it has focus."""
        browser = tabbed_browser_stubs[0]
        browser.widget.current_index = 0
        browser.widget.index_of = 0
        tab.data.pane_active = pane_active
        arg = self._emit(signalfilter.SignalFilter(0), pane)
        assert arg == ('foo' if emitted else None)

    def test_pane_of_another_tab(self, tab, pane, tabbed_browser_stubs):
        """A pane is hidden together with the tab it belongs to."""
        browser = tabbed_browser_stubs[0]
        browser.widget.current_index = 0
        browser.widget.index_of = 1
        tab.data.pane_active = True
        assert self._emit(signalfilter.SignalFilter(0), pane) is None

    def test_pane_looks_up_its_owner(self, tab, pane, tabbed_browser_stubs):
        """A pane isn't in the tab bar, so indexOf() gets the owner."""
        browser = tabbed_browser_stubs[0]
        browser.widget.current_index = 0
        seen = []

        def index_of(widget):
            seen.append(widget)
            return 0

        browser.widget.indexOf = index_of
        tab.data.pane_active = True
        self._emit(signalfilter.SignalFilter(0), pane)
        assert seen == [tab]
