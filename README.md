# A server to collect data from zx303 GPS trackers

zx303 GPS+GPRS module is a cheap and featureful GPS tracker for pets,
children, elderly family members, and, of course, illegal tracking
of people and objects, though the latter absolutely must not be done.

This work is inspired by [this project](https://github.com/tobadia/petGPS),
but is more of a complete reimplementation than a derived work.

As of the time of creation of this README, the program can successfully
collect data and store it in sqlite database, but does not use/provide
location service based on mobile cell and wifi data.
