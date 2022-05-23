# A server to collect data from zx303 ZhongXun Topin Locator

zx303 GPS+GPRS module is a cheap and featureful GPS tracker for pets,
children, elderly family members, and, of course, illegal tracking
of people and objects, though the latter absolutely must not be done.

## Introduction

This work is inspired by [this project](https://github.com/tobadia/petGPS),
but it is more of a complete reimplementation than a derived work.

When powered up, the module makes TCP connection to the configured
(via SMS) server, identifies itself (via IMEI) in the first message,
and continues to send periodic messages with location and other status
updates. Some of these messages require a response from the server.
In particular, when the module has no GPS coverage, it sends information
about neaby GSM+ cell towers and WiFi access points, to which the server
is expected to respond with a message contaning approximate location
derived from this data. To do that, the server may need to consult with
some external service.

Because we would usually want location information reach consumer
instantly upon arrival, and _also_ to be stored, it makes sense to
design the system in "microservices" way, using a message bus with
"publish-subscribe" model. And then, as we already have a message-passing
infrastructure anyway, it makes sense to decouple processes that prepare
responses to the module's messages from the server process that maintains
TCP connections to the modules.

This leads us to the current implementation that has consists of
five daemons that talk to each other via zeromq:

- **collector** that keeps open TCP connections with the terminals
  and publishes received messages _and_ sent responses on the message
  bus,
- **storage** that subscribes to the messages and responses from the
  collector and stores them in a database,
- **termconfig** that subscribes to messages that need non-trivial
  response (most of them are about configuring various settings in
  the terminal, hence the name),
- **lookaside** that subscribes to "rough" location messages, quieries
  an external source (in our implementation, opencellid database),
  and prepares the response to the terminal containing approximated
  location, and
- **wsgateway** that is a websockets server that translaes messages
  between our internal zeromq bus and websocket clients, i.e. web
  pages. This daemon is also capable of responding to http with
  a single html file. This functionality is mainly for debugging.
  Users of this package are expected to implement their own single
  page web application that communicates with this server.

There is also a command-line tool to send messages to the terminal.
A number of useful actions can be initiated in this way.

## Websocket messages

Websockets server communicates with the web page via json encoded
text messages. The only supported message from the web page to the
server is subscription message. Recognized elements are:

- **type** - a string that must be "subscribe"
- **backlog** - an integer specifying how many previous locations to
  send for the start. Limit is per-imei.
- **imei** - a list of 16-character strings with IMEIs of the
  tracker terminals to watch.

Each subscription request nullifies preexisting list of IMEIs
associated with the web client, and replaces it with the list supplied
in the message.

Example of a subscription request:

```
{"imei":["8354369077195199"],
 "type":"subscribe",
 "timestamp":1652134234657,
 "backlog":5}
```

Server sends to the client a backlog of last locations of the
terminals, that it fetches from the database maintained by the
storage service, one location per websocket message. It then
continues to send further messages when they are received from
the module, in real time, including gps location, responses with
approximated location, and status with the precentage of battery
charge.

Example of a location message:

```
{"type": "location",
 "imei": "8354369077195199",
 "timestamp": "2022-05-09 21:52:34.643277+00:00",
 "longitude": 17.465816,
 "latitude": 47.52013,
 "accuracy": "gps"} // or "approximate"
```

Example of a status message

```
{"type": "status",
 "imei": "8354369077195199",
 "timestamp": "2022-05-09 21:52:34.643277+00:00",
 "battery": 46}
```

## Homepage and source

Home page is [http://www.average.org/gps303/](http://www.average.org/gps303/)
Get the source from the origin `git://git.average.org/gps303.git`
or from [Github mirror](https://github.com/crosser/gps303).
