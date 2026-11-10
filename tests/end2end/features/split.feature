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
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """

    Scenario: Commands act on the page after focusing it
        When I open data/numbers/1.txt
        And I run :vsplit http://localhost:(port)/data/numbers/2.txt
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
