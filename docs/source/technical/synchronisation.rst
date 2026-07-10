.. _docs_technical_synchronisation:

**********************
Cross-Device Sync Design
**********************

The cross-device protocol uses Google Drive as a private content store. It is
designed for a desktop application and a native mobile companion that work
offline and exchange changes whenever a connection becomes available.

Google Drive Setup
==================

The desktop and mobile clients must use OAuth clients from the same Google
Cloud project and request only the ``https://www.googleapis.com/auth/drive.appdata``
scope. This stores novelWriter data in Drive's hidden application-data folder;
the application never asks for access to the user's visible files.

OAuth client identifiers and refresh tokens are private credentials. They must
not be committed to the source repository. A distribution must configure its
own consent screen, Android signing certificate and desktop OAuth client.

Project Pairing
===============

The first device uploads a project. A new device must download it with
``ProjectSynchroniser.pull`` before it edits. The download includes the project
tree, document files, manuscript builds, user dictionary and the non-fiction
notebook. Device-local settings, indexes, sessions and lock files are excluded.

Conflict Safety
===============

Each saved file is addressed by its SHA-256 checksum. A revision manifest lists
those immutable objects and the current head is advanced with Drive's HTTP
ETag precondition. When two devices edit separate lines of a document, a
three-way merge combines them. When they edit the same lines, the document is
left with standard conflict markers so that no text is discarded.

The Google Drive API is storage and transport, not a co-editing server. A
production mobile client should synchronise after every local save and when it
returns to the foreground; it must still present a conflict-resolution screen
when a merge is required.

Non-Fiction Notebook
====================

A non-fiction workspace stores structured ``nonfiction.json`` data alongside
the manuscript. It contains topic chapters, process journal entries, sources,
interviews, evidence, reader exercises, chronology, hypotheses and disclosures
which distinguish personal experience from general claims. The file is included
in every synchronised revision.
