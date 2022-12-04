# A server to collect data from GPS Locators

Supported:

* zx303 ZhongXun Topin Locator
  zx303 GPS+GPRS module is a cheap and featureful GPS tracker for pets,
  children, elderly family members, and, of course, illegal tracking
  of people and objects, though the latter absolutely must not be done.
* Some watches-locators, sometimes identified as D99 or similar

## Introduction

This work is inspired by [this project](https://github.com/tobadia/petGPS),
but it is more of a complete re-implementation than a derived work.
There also exists an
[industrial strength open source server](https://www.traccar.org/)
that supports multiple types of trackers.

When powered up, the module makes TCP connection to the configured
(via SMS) server, identifies itself (with IMEI),
and continues to send periodic messages with location and other status
updates. Some of these messages require a response from the server.
In particular, when zx303 has no GPS coverage, it sends information
about nearby GSM+ cell towers and WiFi access points, to which the server
is expected to respond with a message containing approximate location
derived from this data. To do that, the server may need to consult with
some external service.

Because we would usually want location information reach consumer
instantly upon arrival, and _also_ to be stored, it makes sense to
design the system in "microservices" way, using a message bus in
"publish-subscribe" model. And then, since we already have a
message-passing infrastructure anyway, it makes sense to decouple
the server process that maintains TCP connections with the the tracker
terminals from the processes that analyses messages and prepares responses.

This leads us to this implementation, that has consists of five daemons
that talk to each other over Zeromq:

- **collector** that keeps open TCP connections with the terminals
  and publishes received messages _and_ sent responses on the message
  bus,
- **storage** that subscribes to the messages and responses from the
  collector and stores them in a database,
- **termconfig** that subscribes to messages that need nontrivial
  response (most of them are about configuring various settings in
  the terminal, hence the name), and sends responses to the collector
  for relaying to the terminal,
- **rectifier** that subscribes to "rough" location messages, queries
  an external source (in our implementation, either google maps "API",
  or a local opencellid database), optionally sends a response with
  approximated location, and publishes (original or rectified) location
  report reformatted in a unified way, and
- **wsgateway** that is a websockets server that translates messages
  between our internal zeromq bus and websocket clients, i.e. web
  pages. This daemon is also capable of responding to http with
  a single html file. This functionality is mainly for debugging.
  Users of the package are expected to implement their own web
  application that communicates with this server. It also have a
  capability to send a limited number of commands entered via the web
  interface back to the terminal.

There is also a command-line tool to send messages to the terminal.

## Configuring the Terminal

Send SMS to the telephone number of the SIM card plugged in the terminal,
with the text

* for zx303:
  ```
  server#<your_server_address>#<port>#
  ```
* for D99:
  ```
  pw,123456,ip,<your_server_address>,<port>#
  ```

"123456" is the default password on that kind of trackers, that you can
change. If "123456" does not work, try "523681".

Server address may be FQDN or a literal IP address. Port is a number;
by default, this application listens on the port 4303. A different
port can be configured in the config file.

It is recommended to always keep the service running while the terminal
is powered up: it is possible that the terminal is programmed to reset
itself to the default configuration if it cannot connect to the server
for prolonged time.

## Websocket messages

Websockets server communicates with the web page using json encoded
text messages. The only supported message from the web page to the
server is subscription message. Recognised elements are:

- **type** - a string "subscribe", or a command for the terminal.
- **backlog** - for "subscribe, an integer specifying how many
  previous locations to send for the start. Limit is per-imei.
- **imei** - for "subscribe", a list of 10- or 16-character strings
  with IMEIs of the tracker terminals to watch, for other commands -
  IMEI of the particular tracker.
- **txt** - for "msg" command, text of the message to send to the
  terminal, in UTF-8.

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

## Rectifier service

When the terminal has no gps reception, it uses secondary sources of
location hints: list of nearby cell towers, and list of MAC addresses
of nearby WiFi access point, with signal strength. It expects a
response from the server with approximated location. In order to get
such approximation, the server system needs a source of information
about cell towers and/or WiFi access points in the area. We support
two ways to get approximated location: querying Google geolocation
service, and using locally installed database filled with data
downloaded from opencellid crowdsourced source. For both options,
you will need an access token. Google service is "online", you are
making a request for each approximation (and thus reveal location of
your users to Google). Opencellid service is "offline": you download
the file with locations of all cell towers in the country (or worldwide)
once, or refresh it at relatively long intervals, such as a week or a
month, and then all queries are fulfilled locally. Note that opencellid
data does not contain WiFi access points, so the approximation will
less accurate.

Rectifier service can be configured to use either of the options by
assigning `backend = opencellid` or `backend = googlemaps` in the
configuration file (`/etc/loctrkd.conf` by default). Then, the path to
the file with the auth token needs to be specified in the `[opencellid]`
section or `[googlemaps]` section of the configuration file respectively.

Note that in both cases, the value in the configuration file needs
to _point to the file_ that contains the token, rather than contain
the token itself. The file needs to be readable for the user under which
services are executed. That is the user `loctrkd` if this software was
installed as the Debian package.

This part of setup cannot be automated, because each user needs to
obtain their own access token for one of the above services.

## Termconfig Service

To configure terminal settings, such as SOS numbers, update intervals etc.,
"termconfig" service consults the configuration file. It should contain
the section `[termconfig]`, and optionally sections named after the IMEIs
of individual terminals. `[termconfig]` values are used when the individual
section is not present.

For a bigger multi-client setup the user will want to re-implement this
service to use some kind of a database, with the data configurable by the
owners of the terminals.

## Homepage and source

Home page is [http://www.average.org/loctrkd/](http://www.average.org/loctrkd/)
Get the source from the origin `git://git.average.org/loctrkd.git`
or from [Github mirror](https://github.com/crosser/loctrkd).
