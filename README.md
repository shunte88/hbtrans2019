# hbtrans2019

Transcode MythTV content and archive as HEVC
Content is previously transcoded inclusive of removal of commercials

Video content is staged for viewing for a configured period of time
If content is not manually moved or deleted this process transcodes the files to HEVC and saves to a NAS as an archive for later viewing
Handbrake does all of the heavy lifting

Previous versions of the script staged files locally before transcoding and moving to the NAS.
In addition the process utilizes a very simple "lock-file" approach such that multiple instances of the script can perform work. On a prior setup a laptop, the NAS server, and the media server ran in parallel to perform the transcoding as parellel processes.

With more scalable hardware the entire process is perfomed on a single device with additional processes spinning up as required

This is a rewrite of the original 10+ year old code removing redundancy and complexity.

Almost pure python3 only requires the mediainfo and pushbullet packages as additions.

