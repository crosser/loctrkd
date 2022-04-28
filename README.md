# A server to collect data from zx303 ZhongXun Topin Locator

zx303 GPS+GPRS module is a cheap and featureful GPS tracker for pets,
children, elderly family members, and, of course, illegal tracking
of people and objects, though the latter absolutely must not be done.

This work is inspired by [this project](https://github.com/tobadia/petGPS),
but it is more of a complete reimplementation than a derived work.

When powered up, the module makes TCP connection to the configured
(via SMS) server, identifies itself (via IMEI) in the first message,
and continue to send periodic messages with location and other status
updates. Some of these messages require a response from the server.
In particular, when the module has no GPS coverage, it sends information
about neaby GSM+ cell towers and WiFi access points, to which the server
is expected to respond with a message contaning approximate location
derived from this data. That may require querying some external service.

Because we would usually want location information reach consumer
instantly upon arrival, and _also_ to be stored, it makes sense to
design the system in "microservices" way, using a message bus in
"publish-subscribe" model. And then, as we already have a message-
passing infrastructure anyway, it makes sense to decouple processes
that prepare responses to the module's messages from the server that
keeps TCP connections with the modules.

This leads us to the current implementation that has consists of
four daemons that talk to each other via zeromq:

- **collector** that keeps open TCP connections with the terminals
  and publishes received messages,
- **storage** that subscribes to the messages from the collector and
  stores them in a database,
- **termconfig** that subscribes to messages that need non-trivial
  response (most of them are about configuring various settings in
  the terminal, hence the name), and
- **lookaside** that subscribes to "rough" location messages, quieries
  an external source (in our implementation, opencellid database),
  and responds with approximated location.

There is also a command-line tool to send messages to the terminal.
There is a number of useful things that can be requested in this way.
