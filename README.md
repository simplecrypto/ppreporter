ppreporter
==========

A daemon that processes events from PowerPool(s) via a ZeroMQ bridge. This
will provide a more standalone solution for geographic stratums as opposed to
setting up a full SimpleCoin stack just to do share logging. This will also
eliminate the need for the RabbitMQ broker since a broker isn't really needed
for this architecture.
