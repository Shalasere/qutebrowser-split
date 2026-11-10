# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The main tabbed browser widget."""

import os
import signal
import collections
import functools
import weakref
import datetime
import dataclasses
from typing import (
    Any, TypeAlias)
from collections.abc import Mapping, MutableMapping, MutableSequence

from qutebrowser.qt.widgets import QSizePolicy, QWidget, QApplication
from qutebrowser.qt.core import pyqtSignal, pyqtSlot, QTimer, QUrl, QPoint

from qutebrowser.config import config
from qutebrowser.keyinput import modeman
from qutebrowser.mainwindow import tabwidget, mainwindow
from qutebrowser.browser import signalfilter, browsertab, history, inspector
from qutebrowser.utils import (log, usertypes, utils, qtutils,
                               urlutils, message, jinja, version)
from qutebrowser.misc import quitter, objects


@dataclasses.dataclass
class _UndoEntry:

    """Information needed for :undo."""

    url: QUrl
    history: bytes
    index: int
    pinned: bool
    created_at: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now)


UndoStackType: TypeAlias = MutableSequence[MutableSequence[_UndoEntry]]


class TabDeque:

    """Class which manages the 'last visited' tab stack.

    Instead of handling deletions by clearing old entries, they are handled by
    checking if they exist on access. This allows us to save an iteration on
    every tab delete.

    Currently, we assume we will switch to the tab returned by any of the
    getter functions. This is done because the on_switch functions will be
    called upon switch, and we don't want to duplicate entries in the stack
    for a single switch.
    """

    def __init__(self) -> None:
        size = config.val.tabs.focus_stack_size
        if size < 0:
            size = None
        self._stack: collections.deque[weakref.ReferenceType[browsertab.AbstractTab]] = (
            collections.deque(maxlen=size))
        # Items that have been removed from the primary stack.
        self._stack_deleted: list[weakref.ReferenceType[browsertab.AbstractTab]] = []
        self._ignore_next = False
        self._keep_deleted_next = False

    def on_switch(self, old_tab: browsertab.AbstractTab) -> None:
        """Record tab switch events."""
        if self._ignore_next:
            self._ignore_next = False
            self._keep_deleted_next = False
            return
        tab = weakref.ref(old_tab)
        if self._stack_deleted and not self._keep_deleted_next:
            self._stack_deleted = []
        self._keep_deleted_next = False
        self._stack.append(tab)

    def prev(self, cur_tab: browsertab.AbstractTab) -> browsertab.AbstractTab:
        """Get the 'previous' tab in the stack.

        Throws IndexError on failure.
        """
        tab: browsertab.AbstractTab | None = None
        while tab is None or tab.pending_removal or tab is cur_tab:
            tab = self._stack.pop()()
        self._stack_deleted.append(weakref.ref(cur_tab))
        self._ignore_next = True
        return tab

    def next(
        self,
        cur_tab: browsertab.AbstractTab,
        *,
        keep_overflow: bool = True,
    ) -> browsertab.AbstractTab:
        """Get the 'next' tab in the stack.

        Throws IndexError on failure.
        """
        tab: browsertab.AbstractTab | None = None
        while tab is None or tab.pending_removal or tab is cur_tab:
            tab = self._stack_deleted.pop()()
        # On next tab-switch, current tab will be added to stack as normal.
        # However, we shouldn't wipe the overflow stack as normal.
        if keep_overflow:
            self._keep_deleted_next = True
        return tab

    def last(self, cur_tab: browsertab.AbstractTab) -> browsertab.AbstractTab:
        """Get the last tab.

        Throws IndexError on failure.
        """
        try:
            return self.next(cur_tab, keep_overflow=False)
        except IndexError:
            return self.prev(cur_tab)

    def update_size(self) -> None:
        """Update the maxsize of this TabDeque."""
        newsize = config.val.tabs.focus_stack_size
        if newsize < 0:
            newsize = None
        # We can't resize a collections.deque so just recreate it >:(
        self._stack = collections.deque(self._stack, maxlen=newsize)


class TabDeletedError(Exception):

    """Exception raised when _tab_index is called for a deleted tab."""


class TabbedBrowser(QWidget):

    """A TabWidget with QWebViews inside.

    Provides methods to manage tabs, convenience methods to interact with the
    current tab (cur_*) and filters signals to re-emit them when they occurred
    in the currently visible tab.

    For all tab-specific signals (cur_*) emitted by a tab, this happens:
       - the signal gets filtered with _filter_signals and self.cur_* gets
         emitted if the signal occurred in the current tab.

    Attributes:
        search_text/search_options: Search parameters which are shared between
                                    all tabs.
        _win_id: The window ID this tabbedbrowser is associated with.
        _filter: A SignalFilter instance.
        _now_focused: The tab which is focused now.
        _tab_insert_idx_left: Where to insert a new tab with
                              tabs.new_tab_position set to 'prev'.
        _tab_insert_idx_right: Same as above, for 'next'.
        undo_stack: List of lists of _UndoEntry objects of closed tabs.
        is_shutting_down: Whether we're currently shutting down.
        _local_marks: Jump markers local to each page
        _global_marks: Jump markers used across all pages
        default_window_icon: The qutebrowser window icon
        is_private: Whether private browsing is on for this window.

    Signals:
        cur_progress: Progress of the current tab changed (load_progress).
        cur_load_started: Current tab started loading (load_started)
        cur_load_finished: Current tab finished loading (load_finished)
        cur_url_changed: Current URL changed.
        cur_link_hovered: Link hovered in current tab (link_hovered)
        cur_scroll_perc_changed: Scroll percentage of current tab changed.
                                 arg 1: x-position in %.
                                 arg 2: y-position in %.
        cur_load_status_changed: Loading status of current tab changed.
        cur_search_match_changed: The active search match changed.
        close_window: The last tab was closed, close this window.
        resized: Emitted when the browser window has resized, so the completion
                 widget can adjust its size to it.
                 arg: The new size.
        current_tab_changed: The current tab changed to the emitted tab.
        new_tab: Emits the new WebView and its index when a new tab is opened.
        shutting_down: This TabbedBrowser will be deleted soon.
    """

    cur_progress = pyqtSignal(int)
    cur_load_started = pyqtSignal()
    cur_load_finished = pyqtSignal(bool)
    cur_url_changed = pyqtSignal(QUrl)
    cur_link_hovered = pyqtSignal(str)
    cur_scroll_perc_changed = pyqtSignal(int, int)
    cur_load_status_changed = pyqtSignal(usertypes.LoadStatus)
    cur_search_match_changed = pyqtSignal(browsertab.SearchMatch)
    cur_fullscreen_requested = pyqtSignal(bool)
    cur_caret_selection_toggled = pyqtSignal(browsertab.SelectionState)
    close_window = pyqtSignal()
    resized = pyqtSignal('QRect')
    current_tab_changed = pyqtSignal(browsertab.AbstractTab)
    new_tab = pyqtSignal(browsertab.AbstractTab, int)
    shutting_down = pyqtSignal()

    def __init__(self, *, win_id, private, parent=None):
        if private:
            assert not qtutils.is_single_process()
        super().__init__(parent)
        self.widget = tabwidget.TabWidget(win_id, parent=self)
        self._win_id = win_id
        self._tab_insert_idx_left = 0
        self._tab_insert_idx_right = -1
        self.is_shutting_down = False
        self.widget.tabCloseRequested.connect(self.on_tab_close_requested)
        self.widget.new_tab_requested.connect(
            self.tabopen)  # type: ignore[arg-type,unused-ignore]
        self.widget.currentChanged.connect(self._on_current_changed)
        self.cur_fullscreen_requested.connect(self.widget.tab_bar().maybe_hide)

        self.widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if (
            objects.backend == usertypes.Backend.QtWebEngine and
            version.qtwebengine_versions().webengine < utils.VersionNumber(5, 15, 5)
        ):
            # WORKAROUND for https://bugreports.qt.io/browse/QTBUG-65223
            self.cur_load_finished.connect(self._leave_modes_on_load)
        else:
            self.cur_load_started.connect(self._leave_modes_on_load)

        # handle mode_override
        self.current_tab_changed.connect(lambda tab: self._mode_override(tab.url()))
        self.cur_url_changed.connect(self._mode_override)

        # This init is never used, it is immediately thrown away in the next
        # line.
        self.undo_stack: UndoStackType = collections.deque()
        self._update_stack_size()
        self._filter = signalfilter.SignalFilter(win_id, self)
        self._now_focused = None
        self.search_text = None
        self.search_options: Mapping[str, Any] = {}
        self._local_marks: MutableMapping[QUrl, MutableMapping[str, QPoint]] = {}
        self._global_marks: MutableMapping[str, tuple[QPoint, QUrl]] = {}
        self.default_window_icon = self._window().windowIcon()
        self.is_private = private
        self.tab_deque = TabDeque()
        config.instance.changed.connect(self._on_config_changed)
        quitter.instance.shutting_down.connect(self.shutdown)
        app = QApplication.instance()
        assert isinstance(app, QApplication), app
        app.focusChanged.connect(self._on_focus_changed)

    def _update_stack_size(self):
        newsize = config.instance.get('tabs.undo_stack_size')
        if newsize < 0:
            newsize = None
        # We can't resize a collections.deque so just recreate it >:(
        self.undo_stack = collections.deque(self.undo_stack, maxlen=newsize)

    def __repr__(self):
        return utils.get_repr(self, count=self.widget.count())

    @pyqtSlot(str)
    def _on_config_changed(self, option):
        if option == 'tabs.favicons.show':
            self._update_favicons()
        elif option == 'window.title_format':
            self._update_window_title()
        elif option == 'tabs.undo_stack_size':
            self._update_stack_size()
        elif option in ['tabs.title.format', 'tabs.title.format_pinned']:
            self.widget.update_tab_titles()
        elif option == "tabs.focus_stack_size":
            self.tab_deque.update_size()

    def _tab_index(self, tab):
        """Get the index of a given tab.

        Raises TabDeletedError if the tab doesn't exist anymore.
        """
        try:
            idx = self.widget.indexOf(tab)
        except RuntimeError as e:
            log.webview.debug("Got invalid tab ({})!".format(e))
            raise TabDeletedError(e)
        if idx == -1:
            log.webview.debug("Got invalid tab (index is -1)!")
            raise TabDeletedError("index is -1!")
        return idx

    def widgets(self):
        """Get a list of open tab widgets.

        We don't implement this as generator so we can delete tabs while
        iterating over the list.
        """
        widgets = []
        for i in range(self.widget.count()):
            widget = qtutils.add_optional(self.widget.widget(i))
            if widget is None:
                log.webview.debug("Got None-widget in tabbedbrowser!")
            else:
                widgets.append(widget)
        return widgets

    def _update_window_title(self, field=None):
        """Change the window title to match the current tab.

        Args:
            field: A field name which was updated. If given, the title
                   is only set if the given field is in the template.
        """
        title_format = config.cache['window.title_format']
        if field is not None and ('{' + field + '}') not in title_format:
            return

        idx = self.widget.currentIndex()
        if idx == -1:
            # (e.g. last tab removed)
            log.webview.debug("Not updating window title because index is -1")
            return
        fields = self.widget.get_tab_fields(idx)
        fields['id'] = self._win_id

        title = title_format.format(**fields)
        # prevent hanging WMs and similar issues with giant URLs
        title = utils.elide(title, 1024)

        self._window().setWindowTitle(title)

    def _connect_filtered_signals(self, tab):
        """Forward signals of tab (or its pane) to the cur_* signals if shown."""
        tab.link_hovered.connect(
            self._filter.create(self.cur_link_hovered, tab))
        tab.load_progress.connect(
            self._filter.create(self.cur_progress, tab))
        tab.load_finished.connect(
            self._filter.create(self.cur_load_finished, tab))
        tab.load_started.connect(
            self._filter.create(self.cur_load_started, tab))
        tab.scroller.perc_changed.connect(
            self._filter.create(self.cur_scroll_perc_changed, tab))
        tab.url_changed.connect(
            self._filter.create(self.cur_url_changed, tab))
        tab.load_status_changed.connect(
            self._filter.create(self.cur_load_status_changed, tab))
        tab.fullscreen_requested.connect(
            self._filter.create(self.cur_fullscreen_requested, tab))
        tab.caret.selection_toggled.connect(
            self._filter.create(self.cur_caret_selection_toggled, tab))
        tab.search.match_changed.connect(
            self._filter.create(self.cur_search_match_changed, tab))

    def _connect_tab_signals(self, tab):
        """Set up the needed signals for tab."""
        self._connect_filtered_signals(tab)
        tab.shutting_down.connect(
            functools.partial(self._on_tab_shutting_down, tab))
        # misc
        tab.scroller.perc_changed.connect(self._on_scroll_pos_changed)
        tab.scroller.before_jump_requested.connect(lambda: self.set_mark("'"))
        tab.url_changed.connect(
            functools.partial(self._on_url_changed, tab))
        tab.title_changed.connect(
            functools.partial(self._on_title_changed, tab))
        tab.icon_changed.connect(
            functools.partial(self._on_icon_changed, tab))
        tab.pinned_changed.connect(
            functools.partial(self._on_pinned_changed, tab))
        tab.load_progress.connect(
            functools.partial(self._on_load_progress, tab))
        tab.load_finished.connect(
            functools.partial(self._on_load_finished, tab))
        tab.load_started.connect(
            functools.partial(self._on_load_started, tab))
        tab.load_status_changed.connect(
            functools.partial(self._on_load_status_changed, tab))
        tab.window_close_requested.connect(
            functools.partial(self._on_window_close_requested, tab))
        tab.renderer_process_terminated.connect(
            functools.partial(self._on_renderer_process_terminated, tab))
        tab.audio.muted_changed.connect(
            functools.partial(self._on_audio_changed, tab))
        tab.audio.recently_audible_changed.connect(
            functools.partial(self._on_audio_changed, tab))
        tab.new_tab_requested.connect(self.tabopen)
        if not self.is_private:
            tab.history_item_triggered.connect(
                history.web_history.add_from_tab)

    def _current_tab(self) -> browsertab.AbstractTab:
        """Get the current browser tab.

        Note: The assert ensures the current tab is never None.
        """
        tab = self.widget.currentWidget()
        assert isinstance(tab, browsertab.AbstractTab), tab
        return tab

    def _window(self) -> QWidget:
        """Get the current window widget.

        Note: This asserts if there is no window.
        """
        window = self.widget.window()
        assert window is not None
        return window

    def _tab_by_idx(self, idx: int) -> browsertab.AbstractTab | None:
        """Get a browser tab by index.

        If no tab was found at the given index, None is returned.
        """
        tab = self.widget.widget(idx)
        if tab is not None:
            assert isinstance(tab, browsertab.AbstractTab), tab
        return tab

    def current_url(self):
        """Get the URL of the focused page (the split pane or the current tab).

        Intended to be used from command handlers.

        Return:
            The current URL as QUrl.
        """
        tab = self.widget.currentWidget()
        assert tab is None or isinstance(tab, browsertab.AbstractTab), tab
        url = QUrl() if tab is None else tab.active_pane().url()
        qtutils.ensure_valid(url)
        return url

    def _current_tab_url(self):
        """Get the URL of the current tab's page, even if a pane has focus."""
        return self.widget.tab_url(self.widget.currentIndex())

    def current_title(self):
        """Get the title of the focused page (see current_url)."""
        tab = self.widget.currentWidget()
        assert tab is None or isinstance(tab, browsertab.AbstractTab), tab
        page = None if tab is None else tab.active_pane()
        if page is None or page is tab:
            return self.widget.page_title(self.widget.currentIndex())
        return page.title() or page.url().toDisplayString()

    def shutdown(self):
        """Try to shut down all tabs cleanly."""
        self.is_shutting_down = True
        # Reverse tabs so we don't have to recalculate tab titles over and over
        # Removing first causes [2..-1] to be recomputed
        # Removing the last causes nothing to be recomputed
        for idx, tab in enumerate(reversed(self.widgets())):
            self._remove_tab(tab, new_undo=idx == 0)
        self.shutting_down.emit()

    def tab_close_prompt_if_pinned(
            self, tab, force, yes_action,
            text="Are you sure you want to close a pinned tab?"):
        """Helper method for tab_close.

        If tab is pinned, prompt. If not, run yes_action.
        If tab is destroyed, abort question.
        """
        if tab.data.pinned and not force:
            message.confirm_async(
                title='Pinned Tab',
                text=text,
                yes_action=yes_action, default=False, abort_on=[tab.destroyed])
        else:
            yes_action()

    def close_tab(self, tab, *, add_undo=True, new_undo=True, transfer=False):
        """Close a tab.

        Args:
            tab: The QWebView to be closed.
            add_undo: Whether the tab close can be undone.
            new_undo: Whether the undo entry should be a new item in the stack.
            transfer: Whether the tab is closing because it is moving to a new window.
        """
        if config.val.tabs.tabs_are_windows or transfer:
            last_close = 'close'
        else:
            last_close = config.val.tabs.last_close

        count = self.widget.count()

        if last_close == 'ignore' and count == 1:
            return

        self._remove_tab(tab, add_undo=add_undo, new_undo=new_undo)

        if count == 1:  # We just closed the last tab above.
            if last_close == 'close':
                self.close_window.emit()
            elif last_close == 'blank':
                self.load_url(QUrl('about:blank'), newtab=True)
            elif last_close == 'startpage':
                for url in config.val.url.start_pages:
                    self.load_url(url, newtab=True)
            elif last_close == 'default-page':
                self.load_url(config.val.url.default_page, newtab=True)

    def _remove_tab(self, tab, *, add_undo=True, new_undo=True, crashed=False):
        """Remove a tab from the tab list and delete it properly.

        Args:
            tab: The QWebView to be closed.
            add_undo: Whether the tab close can be undone.
            new_undo: Whether the undo entry should be a new item in the stack.
            crashed: Whether we're closing a tab with crashed renderer process.
        """
        idx = self.widget.indexOf(tab)
        if idx == -1:
            if crashed:
                return
            raise TabDeletedError("tab {} is not contained in "
                                  "TabbedWidget!".format(tab))
        if tab is self._now_focused:
            self._now_focused = None

        tab.pending_removal = True

        if tab.url().isEmpty():
            # There are some good reasons why a URL could be empty
            # (target="_blank" with a download, see [1]), so we silently ignore
            # this.
            # [1] https://github.com/qutebrowser/qutebrowser/issues/163
            pass
        elif not tab.url().isValid():
            # We display a warning for URLs which are not empty but invalid -
            # but we don't return here because we want the tab to close either
            # way.
            urlutils.invalid_url_error(tab.url(), "saving tab")
        elif add_undo:
            try:
                history_data = tab.history.private_api.serialize()
            except browsertab.WebTabError:
                pass  # special URL
            else:
                entry = _UndoEntry(url=tab.url(),
                                   history=history_data,
                                   index=idx,
                                   pinned=tab.data.pinned)
                if new_undo or not self.undo_stack:
                    self.undo_stack.append([entry])
                else:
                    self.undo_stack[-1].append(entry)

        tab.private_api.shutdown()
        self.widget.removeTab(idx)

        tab.deleteLater()

    def undo(self, depth=1):
        """Undo removing of a tab or tabs."""
        # Remove unused tab which may be created after the last tab is closed
        last_close = config.val.tabs.last_close
        use_current_tab = False
        last_close_replaces = last_close in [
            'blank', 'startpage', 'default-page'
        ]
        only_one_tab_open = self.widget.count() == 1
        if only_one_tab_open and last_close_replaces:
            tab = self._tab_by_idx(0)
            assert tab is not None
            no_history = len(tab.history) == 1
            urls = {
                'blank': QUrl('about:blank'),
                'startpage': config.val.url.start_pages[0],
                'default-page': config.val.url.default_page,
            }
            first_tab_url = tab.url()
            last_close_urlstr = urls[last_close].toString().rstrip('/')
            first_tab_urlstr = first_tab_url.toString().rstrip('/')
            last_close_url_used = first_tab_urlstr == last_close_urlstr
            use_current_tab = no_history and last_close_url_used

        entries = self.undo_stack[-depth]
        del self.undo_stack[-depth]

        for entry in reversed(entries):
            if use_current_tab:
                newtab = self._tab_by_idx(0)
                assert newtab is not None
                use_current_tab = False
            else:
                newtab = self.tabopen(background=False, idx=entry.index)

            newtab.history.private_api.deserialize(entry.history)
            newtab.set_pinned(entry.pinned)
            newtab.setFocus()

    @pyqtSlot('QUrl', bool)
    def load_url(self, url, newtab):
        """Open a URL, used as a slot.

        Args:
            url: The URL to open as QUrl.
            newtab: True to open URL in a new tab, False otherwise.
        """
        qtutils.ensure_valid(url)
        if newtab or self.widget.currentWidget() is None:
            self.tabopen(url, background=False)
        else:
            self._current_tab().load_url(url)

    @pyqtSlot(int)
    def on_tab_close_requested(self, idx):
        """Close a tab via an index."""
        tab = self._tab_by_idx(idx)
        if tab is None:
            log.webview.debug(
                "Got invalid tab {} for index {}!".format(tab, idx))
            return
        self.tab_close_prompt_if_pinned(
            tab, False, lambda: self.close_tab(tab))

    @pyqtSlot(browsertab.AbstractTab)
    def _on_window_close_requested(self, widget):
        """Close a tab with a widget given."""
        try:
            self.close_tab(widget)
        except TabDeletedError:
            log.webview.debug("Requested to close {!r} which does not "
                              "exist!".format(widget))

    @pyqtSlot('QUrl')
    @pyqtSlot('QUrl', bool)
    @pyqtSlot('QUrl', bool, bool)
    def tabopen(
            self, url: QUrl | None = None,
            background: bool | None = None,
            related: bool = True,
            idx: int | None = None,
    ) -> browsertab.AbstractTab:
        """Open a new tab with a given URL.

        Inner logic for open-tab and open-tab-bg.
        Also connect all the signals we need to _filter_signals.

        Args:
            url: The URL to open as QUrl or None for an empty tab.
            background: Whether to open the tab in the background.
                        if None, the `tabs.background` setting decides.
            related: Whether the tab was opened from another existing tab.
                     If this is set, the new position might be different. With
                     the default settings we handle it like Chromium does:
                         - Tabs from clicked links etc. are to the right of
                           the current (related=True).
                         - Explicitly opened tabs are at the very right
                           (related=False)
            idx: The index where the new tab should be opened.

        Return:
            The opened WebView instance.
        """
        if url is not None:
            qtutils.ensure_valid(url)
        log.webview.debug("Creating new tab with URL {}, background {}, "
                          "related {}, idx {}".format(
                              url, background, related, idx))

        prev_focus = QApplication.focusWidget()

        if config.val.tabs.tabs_are_windows and self.widget.count() > 0:
            window = mainwindow.MainWindow(private=self.is_private)
            tab = window.tabbed_browser.tabopen(
                url=url, background=background, related=related)
            window.show()
            return tab

        tab = browsertab.create(win_id=self._win_id,
                                private=self.is_private,
                                parent=self.widget)
        self._connect_tab_signals(tab)

        if idx is None:
            idx = self._get_new_tab_idx(related)
        self.widget.insertTab(idx, tab, "")

        if url is not None:
            tab.load_url(url)

        if background is None:
            background = config.val.tabs.background
        if background:
            # Make sure the background tab has the correct initial size.
            # With a foreground tab, it's going to be resized correctly by the
            # layout anyways.
            current_widget = self._current_tab()
            tab.resize(current_widget.size())
            self.widget.tab_index_changed.emit(self.widget.currentIndex(),
                                               self.widget.count())
            # Refocus webview in case we lost it by spawning a bg tab
            current_widget.setFocus()
        else:
            self.widget.setCurrentWidget(tab)

        mode = modeman.instance(self._win_id).mode
        if mode in [usertypes.KeyMode.command, usertypes.KeyMode.prompt,
                    usertypes.KeyMode.yesno]:
            # If we were in a command prompt, restore old focus
            # The above commands need to be run to switch tabs
            if prev_focus is not None:
                prev_focus.setFocus()

        tab.show()
        self.new_tab.emit(tab, idx)
        return tab

    def _get_new_tab_idx(self, related):
        """Get the index of a tab to insert.

        Args:
            related: Whether the tab was opened from another tab (as a "child")

        Return:
            The index of the new tab.
        """
        if related:
            pos = config.val.tabs.new_position.related
        else:
            pos = config.val.tabs.new_position.unrelated
        if pos == 'prev':
            if config.val.tabs.new_position.stacking:
                idx = self._tab_insert_idx_left
                # On first sight, we'd think we have to decrement
                # self._tab_insert_idx_left here, as we want the next tab to be
                # *before* the one we just opened. However, since we opened a
                # tab *before* the currently focused tab, indices will shift by
                # 1 automatically.
            else:
                idx = self.widget.currentIndex()
        elif pos == 'next':
            if config.val.tabs.new_position.stacking:
                idx = self._tab_insert_idx_right
            else:
                idx = self.widget.currentIndex() + 1
            self._tab_insert_idx_right += 1
        elif pos == 'first':
            idx = 0
        elif pos == 'last':
            idx = -1
        else:
            raise ValueError("Invalid tabs.new_position '{}'.".format(pos))
        log.webview.debug("tabs.new_position {} -> opening new tab at {}, "
                          "next left: {} / right: {}".format(
                              pos, idx, self._tab_insert_idx_left,
                              self._tab_insert_idx_right))
        return idx

    def _update_favicons(self):
        """Update favicons when config was changed."""
        for tab in self.widgets():
            self.widget.update_tab_favicon(tab)

    @pyqtSlot()
    def _on_load_started(self, tab):
        """Clear icon and update title when a tab started loading.

        Args:
            tab: The tab where the signal belongs to.
        """
        if tab.data.keep_icon:
            tab.data.keep_icon = False
        elif (config.cache['tabs.tabs_are_windows'] and
              tab.data.should_show_icon()):
            self._window().setWindowIcon(self.default_window_icon)

    @pyqtSlot()
    def _on_load_status_changed(self, tab):
        """Update tab/window titles if the load status changed."""
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return

        self.widget.update_tab_title(idx)
        if idx == self.widget.currentIndex():
            self._update_window_title()

    @pyqtSlot()
    def _leave_modes_on_load(self):
        """Leave insert/hint mode when loading started."""
        try:
            url = self.current_url()
            if not url.isValid():
                url = None
        except qtutils.QtValueError:
            url = None
        if config.instance.get('input.insert_mode.leave_on_load',
                               url=url):
            modeman.leave(self._win_id, usertypes.KeyMode.insert,
                          'load started', maybe=True)
        else:
            log.modes.debug("Ignoring leave_on_load request due to setting.")
        if config.cache['hints.leave_on_load']:
            modeman.leave(self._win_id, usertypes.KeyMode.hint,
                          'load started', maybe=True)
        else:
            log.modes.debug("Ignoring leave_on_load request due to setting.")

    @pyqtSlot(browsertab.AbstractTab, str)
    def _on_title_changed(self, tab, text):
        """Set the title of a tab.

        Slot for the title_changed signal of any tab.

        Args:
            tab: The WebView where the title was changed.
            text: The text to set.
        """
        if not text:
            log.webview.debug("Ignoring title change to '{}'.".format(text))
            return
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return
        log.webview.debug("Changing title for idx {} to '{}'".format(
            idx, text))
        self.widget.set_page_title(idx, text)
        if idx == self.widget.currentIndex():
            self._update_window_title()

    @pyqtSlot(browsertab.AbstractTab, QUrl)
    def _on_url_changed(self, tab, url):
        """Set the new URL as title if there's no title yet.

        Args:
            tab: The WebView where the title was changed.
            url: The new URL.
        """
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return

        if not self.widget.page_title(idx):
            self.widget.set_page_title(idx, url.toDisplayString())

    def _mode_override(self, url: QUrl) -> None:
        """Override mode if url matches pattern.

        Args:
            url: The QUrl to match for
        """
        if not url.isValid():
            return
        mode = config.instance.get('input.mode_override', url=url)
        if mode:
            log.modes.debug(f"Mode change to {mode} triggered for url {url}")
            modeman.enter(
                self._win_id,
                usertypes.KeyMode[mode],
                reason='mode_override',
            )

    @pyqtSlot(browsertab.AbstractTab)
    def _on_icon_changed(self, tab):
        """Set the icon of a tab.

        Slot for the iconChanged signal of any tab.

        Args:
            tab: The WebView where the title was changed.
        """
        try:
            self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return
        self.widget.update_tab_favicon(tab)

    def open_pane(self, tab, url, position):
        """Show a split pane next to the page of tab, or move the existing one.

        A pane is a regular tab which isn't in the tab bar. It lives in the
        InspectorSplitter of the tab it belongs to and is destroyed with it.

        Args:
            tab: The tab to add the pane to.
            url: The QUrl to load in the pane, or None to keep its page.
            position: An inspector.Position, the side of the page to put it on.
        """
        splitter = tab.data.splitter
        assert splitter is not None
        pane = tab.data.pane
        created = pane is None
        if pane is None:
            pane = browsertab.create(win_id=self._win_id,
                                     private=self.is_private)
            pane.data.pane_owner = tab
            self._connect_pane_signals(tab, pane)
        try:
            splitter.set_pane(pane, position)
        except inspector.Error:
            if created:
                self._destroy_pane(pane)
            raise
        log.webview.debug(f"Showing pane {pane!r} {position.name} of {tab!r}")
        tab.data.pane = pane
        if url is not None:
            pane.load_url(url)
        self.focus_pane(tab, True)

    def close_pane(self, tab):
        """Remove (and destroy) the split pane of tab."""
        pane = tab.data.pane
        if pane is None:
            return
        log.webview.debug(f"Closing pane {pane!r} of {tab!r}")
        was_active = tab.data.pane_active
        self._set_pane_active(tab, False)
        assert tab.data.splitter is not None
        tab.data.splitter.remove_pane()
        tab.data.pane = None
        self._destroy_pane(pane)
        if was_active:
            tab.setFocus()

    def focus_pane(self, tab, pane_focused):
        """Give focus to the split pane (or back to the page) of tab."""
        target = tab.data.pane if pane_focused else tab
        assert target is not None
        self._set_pane_active(tab, pane_focused)
        target.setFocus()

    def _connect_pane_signals(self, tab, pane):
        """Set up the needed signals for the split pane of tab."""
        self._connect_filtered_signals(pane)
        pane.window_close_requested.connect(
            functools.partial(self.close_pane, tab))
        pane.renderer_process_terminated.connect(
            functools.partial(self._on_pane_renderer_process_terminated, tab))
        pane.new_tab_requested.connect(self.tabopen)
        if not self.is_private:
            pane.history_item_triggered.connect(
                history.web_history.add_from_tab)

    def _destroy_pane(self, pane):
        """Shut down and delete a pane which isn't in a splitter anymore."""
        pane.private_api.shutdown()
        pane.deleteLater()

    def _set_pane_active(self, tab, active):
        """Make commands act on the pane (or the page) of tab."""
        if tab.data.pane_active == active:
            return
        tab.data.pane_active = active
        is_current = tab is self.widget.currentWidget()
        if not is_current:
            # Not shown right now, _on_current_changed handles it later.
            return
        self._leave_modes_on_switch('pane focus changed')
        self.current_tab_changed.emit(tab.active_pane())

    def _on_focus_changed(self, _old, new):
        """Track whether the page or the split pane has focus."""
        # No @pyqtSlot here: on PyQt5 it can't be connected to focusChanged
        # (same as app.on_focus_changed).
        tab = self.widget.currentWidget()
        if (self.is_shutting_down or new is None or
                not isinstance(tab, browsertab.AbstractTab) or
                tab.data.pane is None):
            return
        assert tab.data.splitter is not None
        main = tab.data.splitter.main_widget()
        if tab.data.pane is new or tab.data.pane.isAncestorOf(new):
            self._set_pane_active(tab, True)
        elif main is not None and (main is new or main.isAncestorOf(new)):
            self._set_pane_active(tab, False)

    def _on_tab_shutting_down(self, tab):
        """Destroy the pane of a tab which is being closed."""
        pane = tab.data.pane
        if pane is not None:
            tab.data.pane = None
            tab.data.pane_active = False
            self._destroy_pane(pane)

    def _on_pane_renderer_process_terminated(self, tab, status, _code):
        """Close a split pane whose renderer process terminated."""
        if status == browsertab.TerminationStatus.normal:
            return
        message.error(f"Split pane renderer process terminated "
                      f"({status.name}), closing it.")
        self.close_pane(tab)

    @pyqtSlot(usertypes.KeyMode)
    def on_mode_entered(self, mode):
        """Save input mode when tabs.mode_on_change = restore."""
        if (config.val.tabs.mode_on_change == 'restore' and
                mode in modeman.INPUT_MODES):
            tab = self.widget.currentWidget()
            if tab is not None:
                assert isinstance(tab, browsertab.AbstractTab), tab
                tab.data.input_mode = mode

    @pyqtSlot()
    def on_release_focus(self):
        """Give keyboard focus to the current tab when requested by statusbar/prompt.

        This gets emitted by the statusbar and prompt container before they call .hide()
        on themselves, with the idea that we can explicitly reassign the focus,
        instead of Qt implicitly calling its QWidget::focusNextPrevChild() method,
        finding a new widget to give keyboard focus to.
        """
        widget = qtutils.add_optional(self.widget.currentWidget())
        if widget is None:
            return
        assert isinstance(widget, browsertab.AbstractTab), widget
        widget = widget.active_pane()

        log.modes.debug(f"Focus released, focusing {widget!r}")
        widget.setFocus()

    @pyqtSlot()
    def on_mode_left(self):
        """Save input mode for restoring if needed."""
        if config.val.tabs.mode_on_change != 'restore':
            return

        widget = qtutils.add_optional(self.widget.currentWidget())
        if widget is None:
            return

        assert isinstance(widget, browsertab.AbstractTab), widget
        widget.data.input_mode = usertypes.KeyMode.normal

    def _leave_modes_on_switch(self, reason):
        """Leave the modes which shouldn't carry over to another tab or pane."""
        modes_to_leave = [usertypes.KeyMode.hint, usertypes.KeyMode.caret]
        if config.val.tabs.mode_on_change == 'normal':
            modes_to_leave += modeman.INPUT_MODES
        for mode in modes_to_leave:
            modeman.leave(self._win_id, mode, reason, maybe=True)

    @pyqtSlot(int)
    def _on_current_changed(self, idx):
        """Add prev tab to stack and leave hinting mode when focus changed."""
        mode_on_change = config.val.tabs.mode_on_change
        if idx == -1 or self.is_shutting_down:
            # closing the last tab (before quitting) or shutting down
            return
        tab = self._tab_by_idx(idx)
        if tab is None:
            log.webview.debug(
                "on_current_changed got called with invalid index {}"
                .format(idx))
            return

        log.modes.debug("Current tab changed, focusing {!r}".format(tab))
        tab.active_pane().setFocus()

        mm_instance = modeman.instance(self._win_id)
        current_mode = mm_instance.mode
        log.modes.debug("Mode before tab change: {} (mode_on_change = {})"
                        .format(current_mode.name, mode_on_change))
        self._leave_modes_on_switch('tab changed')
        if (mode_on_change == 'restore' and
                current_mode not in modeman.PROMPT_MODES):
            modeman.enter(self._win_id, tab.data.input_mode, 'restore')
        if self._now_focused is not None:
            self.tab_deque.on_switch(self._now_focused)
        log.modes.debug("Mode after tab change: {} (mode_on_change = {})"
                        .format(current_mode.name, mode_on_change))
        self._now_focused = tab
        self.current_tab_changed.emit(tab.active_pane())
        self.cur_search_match_changed.emit(tab.search.match)
        QTimer.singleShot(0, self._update_window_title)
        self._tab_insert_idx_left = self.widget.currentIndex()
        self._tab_insert_idx_right = self.widget.currentIndex() + 1

    @pyqtSlot()
    def on_cmd_return_pressed(self):
        """Set focus when the commandline closes."""
        log.modes.debug("Commandline closed, focusing {!r}".format(self))

    def _on_load_progress(self, tab, perc):
        """Adjust tab indicator on load progress."""
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return
        start = config.cache['colors.tabs.indicator.start']
        stop = config.cache['colors.tabs.indicator.stop']
        system = config.cache['colors.tabs.indicator.system']
        color = qtutils.interpolate_color(start, stop, perc, system)
        self.widget.set_tab_indicator_color(idx, color)
        self.widget.update_tab_title(idx)
        if idx == self.widget.currentIndex():
            self._update_window_title()

    def _on_load_finished(self, tab, ok):
        """Adjust tab indicator when loading finished."""
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return
        if ok:
            start = config.cache['colors.tabs.indicator.start']
            stop = config.cache['colors.tabs.indicator.stop']
            system = config.cache['colors.tabs.indicator.system']
            color = qtutils.interpolate_color(start, stop, 100, system)
        else:
            color = config.cache['colors.tabs.indicator.error']
        self.widget.set_tab_indicator_color(idx, color)
        if idx == self.widget.currentIndex():
            tab.private_api.handle_auto_insert_mode(ok)

    @pyqtSlot()
    def _on_scroll_pos_changed(self):
        """Update tab and window title when scroll position changed."""
        idx = self.widget.currentIndex()
        if idx == -1:
            # (e.g. last tab removed)
            log.webview.debug("Not updating scroll position because index is "
                              "-1")
            return
        self._update_window_title('scroll_pos')
        self.widget.update_tab_title(idx, 'scroll_pos')

    def _on_pinned_changed(self, tab):
        """Update the tab's pinned status."""
        idx = self.widget.indexOf(tab)
        self.widget.update_tab_favicon(tab)
        self.widget.update_tab_title(idx)

    def _on_audio_changed(self, tab, _muted):
        """Update audio field in tab when mute or recentlyAudible changed."""
        try:
            idx = self._tab_index(tab)
        except TabDeletedError:
            # We can get signals for tabs we already deleted...
            return
        self.widget.update_tab_title(idx, 'audio')
        if idx == self.widget.currentIndex():
            self._update_window_title('audio')

    def _on_renderer_process_terminated(self, tab, status, code):
        """Show an error when a renderer process terminated."""
        if status == browsertab.TerminationStatus.normal:
            return

        messages = {
            browsertab.TerminationStatus.abnormal: "Renderer process exited",
            browsertab.TerminationStatus.crashed: "Renderer process crashed",
            browsertab.TerminationStatus.killed: "Renderer process was killed",
            browsertab.TerminationStatus.unknown: "Renderer process did not start",
        }

        sig = None
        try:
            if os.WIFSIGNALED(code):
                sig = signal.Signals(os.WTERMSIG(code))
        except (AttributeError, ValueError):
            pass

        if sig is not None:
            msg = messages[status] + f" (status {code}: {sig.name})"
        else:
            msg = messages[status] + f" (status {code})"

        # WORKAROUND for https://bugreports.qt.io/browse/QTBUG-91715
        versions = version.qtwebengine_versions()
        if (
            status == browsertab.TerminationStatus.unknown and
            code == 1002 and
            versions.webengine == utils.VersionNumber(5, 15, 3)
        ):
            log.webview.error(msg)
            log.webview.error('')
            log.webview.error(
                'NOTE: If you see this and "Network service crashed, restarting '
                'service.", please see:')
            log.webview.error('https://github.com/qutebrowser/qutebrowser/issues/6235')
            log.webview.error(
                'You can set the "qt.workarounds.locale" setting in qutebrowser to '
                'work around the issue.')
            log.webview.error(
                'A proper fix is likely available in QtWebEngine soon (which is why '
                'the workaround is disabled by default).')
            log.webview.error('')
            return

        def show_error_page(html):
            tab.set_html(html)
            log.webview.error(msg)

        url_string = tab.url(requested=True).toDisplayString()
        error_page = jinja.render(
            'error.html', title="Error loading {}".format(url_string),
            url=url_string, error=msg)
        QTimer.singleShot(100, lambda: show_error_page(error_page))

    def resizeEvent(self, e):
        """Extend resizeEvent of QWidget to emit a resized signal afterwards.

        Args:
            e: The QResizeEvent
        """
        super().resizeEvent(e)
        self.resized.emit(self.geometry())

    def wheelEvent(self, e):
        """Override wheelEvent of QWidget to forward it to the focused tab.

        Args:
            e: The QWheelEvent
        """
        if self._now_focused is not None:
            self._now_focused.wheelEvent(e)
        else:
            e.ignore()

    def set_mark(self, key):
        """Set a mark at the current scroll position in the current tab.

        Args:
            key: mark identifier; capital indicates a global mark
        """
        # strip the fragment as it may interfere with scrolling
        try:
            # Marks always belong to the page, not to a split pane.
            url = self._current_tab_url().adjusted(
                QUrl.UrlFormattingOption.RemoveFragment)
        except qtutils.QtValueError:
            # show an error only if the mark is not automatically set
            if key != "'":
                message.error("Failed to set mark: url invalid")
            return
        point = self._current_tab().scroller.pos_px()

        if key.isupper():
            self._global_marks[key] = point, url
        else:
            if url not in self._local_marks:
                self._local_marks[url] = {}
            self._local_marks[url][key] = point

    def jump_mark(self, key):
        """Jump to the mark named by `key`.

        Args:
            key: mark identifier; capital indicates a global mark
        """
        try:
            # consider urls that differ only in fragment to be identical
            urlkey = self._current_tab_url().adjusted(
                QUrl.UrlFormattingOption.RemoveFragment)
        except qtutils.QtValueError:
            urlkey = None

        tab = self._current_tab()

        if key.isupper():
            if key in self._global_marks:
                point, url = self._global_marks[key]

                def callback(ok):
                    """Scroll once loading finished."""
                    if ok:
                        self.cur_load_finished.disconnect(callback)
                        tab.scroller.to_point(point)

                self.load_url(url, newtab=False)
                self.cur_load_finished.connect(callback)
            else:
                message.error("Mark {} is not set".format(key))
        elif urlkey is None:
            message.error("Current URL is invalid!")
        elif urlkey in self._local_marks and key in self._local_marks[urlkey]:
            point = self._local_marks[urlkey][key]

            # save the pre-jump position in the special ' mark
            # this has to happen after we read the mark, otherwise jump_mark
            # "'" would just jump to the current position every time
            tab.scroller.before_jump_requested.emit()
            tab.scroller.to_point(point)
        else:
            message.error("Mark {} is not set".format(key))
