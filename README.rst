Waitlist Manager
================

This is a plugin for `pretix`_.

It adds an event-level backend tool to manage selected product waitlists by
querying pretix models directly inside the same installation.

Configuration / Usage
---------------------

1. Enable the plugin for an event in ``Settings > Plugins``.
2. Open ``Waitlist manager`` in the event sidebar.
3. Use the ``Import`` panel to select:

   * a membership type
   * a question option to match
   * a target product or product variation
   * an event date, if the event is a series

4. Run a dry run first, then run the actual import.
5. Use the ``Randomize`` panel to:

   * select a waitlist target
   * optionally limit randomization to entries registered on or before a cutoff date
   * optionally group related entries by a free-text question containing email addresses

Current scope
-------------

The import panel currently matches against choice-based questions
(single-choice and multiple-choice) by checking existing order-position answers
for customers that hold an active membership of the selected membership type.
Waitlist targets are limited to active products and active variations with
waiting lists enabled.

The randomize panel rewrites the integer ``priority`` field on selected waiting
list entries. pretix then applies its normal ordering rules on top of those new
priority values.

Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_.
2. Clone this repository.
3. Activate the virtual environment you use for pretix development.
4. Execute ``pip install -e .`` within this directory.
5. Restart your local pretix server.

License
-------

Copyright 2026 Jesse

Released under the terms of the Apache License 2.0

.. _pretix: https://github.com/pretix/pretix
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
