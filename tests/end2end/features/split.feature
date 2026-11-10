Feature: Split panes
    A split pane shows a second page next to the page of a tab.

    Background:
        Given I clean up open tabs
        And I set tabs.tabs_are_windows to false
        And I clear the log

    Scenario: Opening a pane with a URL
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        Then data/numbers/2.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Opening a horizontal pane with a URL
        When I open data/numbers/1.txt
        And I run :hsplit http://localhost:(port)/data/numbers/2.txt
        Then data/numbers/2.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Opening a pane without a URL shows the current page
        When I open data/numbers/1.txt
        And I run :vsplit
        Then data/numbers/1.txt should be loaded

    Scenario: Opening a pane with an invalid URL
        When I set url.auto_search to never
        And I open data/numbers/1.txt
        And I run :vsplit foo!
        Then the error "Invalid URL" should be shown

    Scenario: Moving an existing pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I run :hsplit
        Then the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Commands act on the focused pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Commands act on the page after focusing it
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :split-focus
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/3.txt (active)
            """

    Scenario: Focusing the pane again
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :split-focus
        And I run :split-focus
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Going back in the pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :open http://localhost:(port)/data/numbers/3.txt
        And I wait until data/numbers/3.txt is loaded
        And I run :back
        Then data/numbers/2.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Closing the pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I run :split-close
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/3.txt (active)
            """

    Scenario: Closing a pane which doesn't exist
        When I open data/numbers/1.txt
        And I run :split-close
        Then the error "No split pane in this tab" should be shown

    Scenario: Focusing a pane which doesn't exist
        When I open data/numbers/1.txt
        And I run :split-focus
        Then the error "No split pane in this tab" should be shown

    Scenario: Closing a tab with a pane
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :vsplit http://localhost:(port)/data/numbers/3.txt
        And I run :tab-close
        Then the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Switching tabs with a pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I open data/numbers/3.txt in a new tab
        And I run :tab-prev
        And I run :open http://localhost:(port)/data/numbers/4.txt
        Then data/numbers/4.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/3.txt
            """

    Scenario: Opening the devtools in a tab with a pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I run :split-focus
        And I run :devtools
        Then the error "Can't open the devtools in a tab with a split pane" should be shown

    Scenario: Opening a pane in a tab with devtools
        When I open data/numbers/1.txt
        And I run :devtools
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        Then the error "Can't split a tab which has docked devtools" should be shown

    Scenario: Opening a pane in a private window
        When I open data/numbers/1.txt in a private window
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        Then data/numbers/2.txt should be loaded

    # Layout

    Scenario: A vertical split shows the pane next to the page
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        Then the pane should be right of the page

    Scenario: A horizontal split shows the pane below the page
        When I open data/numbers/1.txt
        And I run :hsplit http://localhost:(port)/data/numbers/2.txt
        Then the pane should be below the page

    # Commands which use the URL of the page

    Scenario: Yanking the URL of the pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :yank
        Then the message "Yanked URL to clipboard: http://localhost:(port)/data/numbers/2.txt" should be shown

    Scenario: Yanking the URL after focusing the page
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :split-focus
        And I run :yank
        Then the message "Yanked URL to clipboard: http://localhost:(port)/data/numbers/1.txt" should be shown

    Scenario: Using {url} while the pane has focus
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :message-info {url}
        Then the message "http://localhost:(port)/data/numbers/2.txt" should be shown

    Scenario: Incrementing the URL of the pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/3.txt
        And I wait until data/numbers/3.txt is loaded
        And I run :navigate increment
        Then data/numbers/4.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Cloning the tab while the pane has focus
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :tab-clone
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/2.txt (active)
            """

    # Status bar

    Scenario: The status bar shows the pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        Then the status bar URL should end with /data/numbers/2.txt

    Scenario: The status bar shows the pane again after switching tabs
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I open data/numbers/3.txt in a new tab
        And I run :tab-prev
        Then the status bar URL should end with /data/numbers/2.txt

    Scenario: Closing the pane of a background tab leaves the status bar alone
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I open data/numbers/3.txt in a new tab
        And the pane of tab 1 is closed in the background
        Then the status bar URL should end with /data/numbers/3.txt

    # Moving tabs between windows

    Scenario: Giving a tab with a pane to another window
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :vsplit http://localhost:(port)/data/numbers/3.txt
        And I run :tab-give
        Then the error "Can't give a tab with a split pane" should be shown

    Scenario: Giving a tab with a pane to another window, keeping it
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        And I run :tab-give --keep
        Then data/numbers/2.txt should be loaded

    Scenario: Taking a tab with a pane from another window
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I open data/numbers/3.txt in a new window
        And I run :tab-take numbers/1.txt
        Then the error "Can't take a tab with a split pane" should be shown

    # Abuse

    Scenario: Closing and reopening a pane in one go
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt ;; split-close ;; vsplit http://localhost:(port)/data/numbers/3.txt ;; split-close
        And I run :open http://localhost:(port)/data/numbers/4.txt
        Then data/numbers/4.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/4.txt (active)
            """

    Scenario: Opening and closing panes repeatedly doesn't leak tabs
        When I open data/numbers/1.txt
        And I open and close a pane 15 times
        Then there should be 1 tab objects

    Scenario: Quitting with a pane
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
        And I run :quit
        Then qutebrowser should quit
