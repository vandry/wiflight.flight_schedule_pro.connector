Integration between Flight Schedule Pro and Wi-Flight
=====================================================

Overview
--------

[Wi-Flight](https://www.wi-flight.net) is an automated flight data
collection and monitoring system with web-based flight playback
capability. Wi-Flight uses flight data recorders aboard aircraft that
upload their data over the Internet.

[Flight Schedule Pro](http://www.flightschedulepro.com/) is an online
aircraft scheduling system.

This connector implements one-way integration between these two systems.
Wi-Flight receives notification of aircraft reservations from Flight
Schedule Pro. Wi-Flight's normal matching between flights and
reservations takes place so that when Wi-Flight flights are recorded and
uploaded, they are associated with the corresponding Flight Schedule Pro
reservation. The primary benefit of implementing such integration is
that the crew information supplied by Flight Schedule Pro is available
to Wi-Flight and the crew can be automatically offered access to their
flights in Wi-Flight.

Implementation
--------------

This is actually a really horrible example of integration between
Wi-Flight and another piece of software and generally an example of
what NOT to do. In summary, it's an ugly hack :-(

The connector was implemented as-is anyway because Flight Schedule
Pro is popular with Wi-Flight customers, and they do not appear to
be open to improving their integration capability.

Some of the features of this connector that are unfortunate are:

- Uses email to receive notifications. Email is neither secure nor
reliable. An HTTPS-based protocol which queues notifications until
they are acknowledged by the other end would be an example of a
better protocol.

- Uses local time in notifications. Local time requires extra
configuration to make sure the connector maps the time back to UTC
using the same timezone as Flight Schedule Pro used to map it to
local time in the first place. Plus, local times can be ambiguous
when rule changes and DST changes occur. UTC would have been a
better choice for the notifications from Flight Schedule Pro.

- Only gives crew's full names in the reservation notification. No
email address or other type of usable key that would facilitate
automatically creating Wi-Flight users from Flight Schedule Pro crew
members.

How to use
----------

Incoming mails from Flight Schedule Pro must be piped into the
"receive" script, running under a user that has access to read the
configuration, preferably a dedicated user. How to do this is
dependant on email software (Postfix, exim, etc...).

The first argument to the "receive" script must be a mailbox
identifier. This can be used so that different fleets in Flight
Schedule Pro send notifications to different email addresses,
which lead to different mailbox identifiers and to different
configuration profiles of the connector.

The connector writes nothing to local storage and keeps no state at all,
so it is OK to run multiple non-communicating instances of the
connector for high availability.

For each mailbox identifier (first argument to "receive"), there should
be a configuration file in ~/fsp_config with filename identical to the
mailbox identifier. The configuration file should contain something like
this:

    # required
    user <Wi-Flight API username>
    timezone America/Montreal
    # optional, otherwise default is used
    url <Wi-Flight API URL>

There should also be a file with the same name in ~/.fsp_password with
the Wi-Flight API password on one line.
